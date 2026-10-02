#!/usr/bin/env python3
"""
Pipeline Electoral 2027 - Soacha
Análisis de sentimiento: YouTube + TikTok → JSON para GitHub Pages

Lee comentarios de YouTube y TikTok, clasifica sentimiento con Claude Haiku,
detecta temas, y genera un JSON listo para soacha-2027.html

Requiere:
- yt_comments_raw.csv (YouTube)
- tiktok_comments_raw.csv (TikTok)
- Variables de entorno: ANTHROPIC_API_KEY

Uso:
    python 23_youtube_tiktok_sentimiento_unificado.py
"""

import csv
import json
import os
from datetime import datetime
from collections import defaultdict
import anthropic

# ===== CONFIG =====
YOUTUBE_CSV = "yt_comments_raw.csv"
TIKTOK_CSV = "tiktok_comments_raw.csv"
OUTPUT_JSON = "data/sentimiento_soacha.json"
MODELO = "claude-haiku-4-5-20251001"

# Mapeo de sentimientos a scores
SCORE_MAP = {
    "POSITIVO": 0.8,
    "NEUTRAL": 0.0,
    "NEGATIVO": -0.8,
}

# Cliente Anthropic
api_key = os.getenv("ANTHROPIC_API_KEY")
if not api_key:
    raise ValueError("⚠️  Variable ANTHROPIC_API_KEY no configurada")

client = anthropic.Anthropic(api_key=api_key)


def classify_sentiment(text):
    """
    Clasifica sentimiento y detecta tema del comentario usando Claude Haiku.
    Retorna: (sentimiento, score, tema)
    """
    try:
        prompt = f"""Analiza este comentario electoral y clasifica:

Comentario: "{text}"

Responde EXACTAMENTE en este formato JSON (sin markdown):
{{"sentimiento": "POSITIVO|NEUTRAL|NEGATIVO", "tema": "Gestión|Seguridad|Infraestructura|Corrupción|Otro", "razon": "breve explicación"}}

Sé estricto: comentarios críticos o sarcásticos = NEGATIVO. Solo aprobación genuina = POSITIVO."""

        message = client.messages.create(
            model=MODELO,
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}]
        )
        
        result_text = message.content[0].text.strip()
        
        # Limpiar markdown si existe
        if result_text.startswith("```"):
            result_text = result_text.split("```")[1].replace("json", "").strip()
        
        result = json.loads(result_text)
        sentimiento = result.get("sentimiento", "NEUTRAL").upper()
        tema = result.get("tema", "Otro")
        score = SCORE_MAP.get(sentimiento, 0.0)
        
        return sentimiento, score, tema
    except Exception as e:
        print(f"  [!] Error clasificando: {str(e)[:60]}")
        return "NEUTRAL", 0.0, "Otro"


def load_and_process_comments(platform_csv, platform_name):
    """
    Carga CSV de comentarios (YouTube o TikTok) y clasifica sentimientos.
    Retorna dict: {candidato: [comentarios clasificados]}
    """
    
    comments_by_candidate = defaultdict(list)
    
    if not os.path.exists(platform_csv):
        print(f"  [!] {platform_name} CSV no encontrado: {platform_csv}")
        return comments_by_candidate
    
    print(f"\n[>] Procesando {platform_name}: {platform_csv}")
    
    with open(platform_csv, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            candidate = row.get('candidate', '').upper()
            text = row.get('text', '')
            video_id = row.get('video_id', '')
            
            if not candidate or not text:
                continue
            
            # Clasificar
            sentimiento, score, tema = classify_sentiment(text)
            
            comment_obj = {
                'plataforma': platform_name.lower(),
                'fecha': row.get('published_at', ''),
                'score': score,
                'sentimiento': sentimiento,
                'tema': tema,
                'texto': text[:150],
                'autor': row.get('author', ''),
                'likes': int(row.get('likes', 0)) if row.get('likes') else 0,
                'replies': int(row.get('reply_count', 0)) if row.get('reply_count') else 0,
                'video_id': video_id,
            }
            
            comments_by_candidate[candidate].append(comment_obj)
            print(f"  [{sentimiento:8s}] {tema:15s} | {text[:50]}...")
    
    return comments_by_candidate


def compute_stats(comments_list):
    """
    Calcula estadísticas de una lista de comentarios.
    """
    if not comments_list:
        return {
            'sentimiento_promedio': 0.0,
            'tendencia': 'estable',
            'toxicidad_pct': 0,
            'temas': [],
        }
    
    # Score promedio
    scores = [c['score'] for c in comments_list]
    promedio = sum(scores) / len(scores) if scores else 0.0
    
    # Tendencia (si hay variación)
    if len(scores) > 1:
        if promedio >= 0.2:
            tendencia = 'sube'
        elif promedio <= -0.2:
            tendencia = 'baja'
        else:
            tendencia = 'estable'
    else:
        tendencia = 'estable'
    
    # Toxicidad = % de NEGATIVO
    negativos = sum(1 for c in comments_list if c['score'] < 0)
    toxicidad_pct = int((negativos / len(comments_list)) * 100) if comments_list else 0
    
    # Temas
    tema_counts = defaultdict(lambda: {'count': 0, 'scores': []})
    for c in comments_list:
        tema = c['tema']
        tema_counts[tema]['count'] += 1
        tema_counts[tema]['scores'].append(c['score'])
    
    temas = []
    for tema, data in tema_counts.items():
        avg_score = sum(data['scores']) / len(data['scores'])
        temas.append({
            'tema': tema,
            'score': round(avg_score, 2),
            'menciones': data['count'],
        })
    
    temas.sort(key=lambda x: abs(x['score']), reverse=True)
    
    return {
        'sentimiento_promedio': round(promedio, 2),
        'tendencia': tendencia,
        'toxicidad_pct': toxicidad_pct,
        'temas': temas[:3],  # Top 3 temas
    }


def merge_platforms_data(yt_data, tk_data):
    """
    Fusiona datos de YouTube y TikTok por candidato.
    """
    all_candidates = set(list(yt_data.keys()) + list(tk_data.keys()))
    merged = {}
    
    for candidate in all_candidates:
        yt_comments = yt_data.get(candidate, [])
        tk_comments = tk_data.get(candidate, [])
        all_comments = yt_comments + tk_comments
        
        if not all_comments:
            continue
        
        # Stats generales
        stats = compute_stats(all_comments)
        
        # Posts por plataforma
        yt_posts = len(set(c['video_id'] for c in yt_comments)) if yt_comments else 0
        tk_posts = len(set(c['video_id'] for c in tk_comments)) if tk_comments else 0
        
        merged[candidate] = {
            'es_cliente': candidate == "DANNY CAICEDO",
            'partido': {
                "DANNY CAICEDO": "Concejal de oposición",
                "JULIAN SANCHE PERICO": "Alcalde actual",
                "GIOVANNI RAMIREZ MOYA": "Concejal",
            }.get(candidate, "Candidato"),
            'sentimiento_promedio': stats['sentimiento_promedio'],
            'tendencia': stats['tendencia'],
            'total_posts': yt_posts + tk_posts,
            'total_comentarios': len(all_comments),
            'toxicidad_pct': stats['toxicidad_pct'],
            'alerta_toxicidad': stats['toxicidad_pct'] >= 70,
            'por_plataforma': {
                'youtube': {
                    'score': compute_stats(yt_comments)['sentimiento_promedio'],
                    'posts': yt_posts,
                    'comentarios': len(yt_comments),
                } if yt_comments else {'score': 0, 'posts': 0, 'comentarios': 0},
                'tiktok': {
                    'score': compute_stats(tk_comments)['sentimiento_promedio'],
                    'posts': tk_posts,
                    'comentarios': len(tk_comments),
                } if tk_comments else {'score': 0, 'posts': 0, 'comentarios': 0},
            },
            'temas': stats['temas'],
            'serie': [{'f': datetime.now().strftime('%d %b'), 's': stats['sentimiento_promedio']}],
            'posts_destacados': [
                {
                    'plataforma': c['plataforma'],
                    'fecha': c['fecha'][:10],
                    'score': c['score'],
                    'resumen': c['texto'],
                    'tema': c['tema'],
                    'comentarios': c['replies'],
                    'comentario_pos': '',
                    'comentario_neg': c['texto'] if c['score'] < 0 else '',
                }
                for c in sorted(all_comments, key=lambda x: x['likes'], reverse=True)[:3]
            ],
        }
    
    return merged


def generate_json_output(merged_data):
    """
    Genera JSON en formato exacto que espera soacha-2027.html
    """
    output = {
        'meta': {
            'generado': datetime.now().isoformat(),
            'fuente': 'YouTube + TikTok (Apify Scraper)',
            'ventana': 'últimos 30 días',
            'total_comentarios': sum(d['total_comentarios'] for d in merged_data.values()),
            'modelo': MODELO,
        },
        'candidatos': merged_data,
    }
    
    return output


def main():
    print("="*70)
    print("Pipeline Electoral 2027 - Soacha")
    print("YouTube + TikTok → Análisis de Sentimiento → JSON")
    print("="*70)
    
    # 1. Cargar y procesar YouTube
    yt_data = load_and_process_comments(YOUTUBE_CSV, "YouTube")
    
    # 2. Cargar y procesar TikTok
    tk_data = load_and_process_comments(TIKTOK_CSV, "TikTok")
    
    # 3. Fusionar plataformas
    print("\n[>] Fusionando plataformas...")
    merged = merge_platforms_data(yt_data, tk_data)
    
    # 4. Generar JSON
    print("[>] Generando JSON...")
    output_json = generate_json_output(merged)
    
    # 5. Guardar
    os.makedirs("data", exist_ok=True)
    with open(OUTPUT_JSON, 'w', encoding='utf-8') as f:
        json.dump(output_json, f, ensure_ascii=False, indent=2)
    
    print(f"\n[✓] JSON guardado: {OUTPUT_JSON}")
    print(f"\n[✓] Resumen final:")
    for candidate, data in merged.items():
        print(f"  {candidate:30s} | Score: {data['sentimiento_promedio']:+.2f} | Comentarios: {data['total_comentarios']:2d} | Toxicidad: {data['toxicidad_pct']:3d}%")
    
    print(f"\n[✓] Listo para GitHub Pages push 🚀")


if __name__ == "__main__":
    main()
