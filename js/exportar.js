/* Exportación a Excel, PDF y CSV para las páginas del panel.
   Uso:
     XEXP.registrar("clave", () => ({ titulo, subtitulo, hojas: [{ nombre, columnas: [[titulo, tipo, ancho]], filas: [[...]] }] }));
     elemento.innerHTML = XEXP.botones("clave");
   tipo de columna: t texto, m pesos, n número entero, d número con un decimal, p proporción (0-1), f fecha.
   Un cuarto elemento true en la columna la deja fuera del PDF (queda en Excel y CSV).
   Las librerías (js/vendor) solo se descargan la primera vez que se exporta. */
(function () {
  "use strict";
  const LIBS = { xlsx: ["/js/vendor/xlsx.full.min.js"], pdf: ["/js/vendor/jspdf.umd.min.js", "/js/vendor/jspdf.plugin.autotable.min.js"] };
  const cargadas = {}, vistas = {};
  const FUENTES = "Fuentes: SECOP II y SECOP I (Colombia Compra Eficiente), RUES (Confecámaras), SIRI (Procuraduría) y Boletín de Responsables Fiscales (Contraloría), vía datos.gov.co.";
  const AVISO = "Las alertas son indicios para revisar, no conclusiones. Verifique cada caso en el documento oficial antes de usarlo.";

  function cargarLib(k) {
    if (!cargadas[k]) cargadas[k] = LIBS[k].reduce((p, src) => p.then(() => new Promise((ok, mal) => {
      const s = document.createElement("script"); s.src = src; s.onload = ok;
      s.onerror = () => mal(new Error("No se pudo cargar " + src)); document.head.appendChild(s);
    })), Promise.resolve()).catch(e => { cargadas[k] = null; throw e; });
    return cargadas[k];
  }
  const slug = t => String(t || "informe").toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "")
    .replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "").slice(0, 90);
  const ahora = () => new Date().toLocaleString("es-CO");
  const peso = v => "$" + Math.round(+v || 0).toLocaleString("es-CO");
  const fmt = (x, t) => x === "" || x == null ? "" : t === "m" ? peso(x) : t === "n" ? (+x).toLocaleString("es-CO")
    : t === "d" ? (+x).toLocaleString("es-CO", { minimumFractionDigits: 1, maximumFractionDigits: 1 })
    : t === "p" ? (x * 100).toLocaleString("es-CO", { maximumFractionDigits: 1 }) + "%" : String(x);
  const limpio = x => x == null || (typeof x === "number" && isNaN(x)) ? "" : x;

  function descargar(blob, nombre) {
    const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = nombre;
    document.body.appendChild(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(a.href), 4000);
  }

  function aExcel(V) {
    const X = window.XLSX, wb = X.utils.book_new();
    const wp = X.utils.aoa_to_sheet([["X-irin Technologies S.A.S. · Estrategia Electoral 2027"], [V.titulo], [V.subtitulo || ""],
      ["Generado: " + ahora()], [], [FUENTES], [AVISO]]);
    wp["!cols"] = [{ wch: 120 }]; X.utils.book_append_sheet(wb, wp, "Portada");
    const usados = new Set();
    V.hojas.forEach(h => {
      const ws = X.utils.aoa_to_sheet([h.columnas.map(c => c[0]), ...h.filas.map(f => f.map(limpio))]);
      ws["!cols"] = h.columnas.map(c => ({ wch: c[2] || 14 }));
      ws["!autofilter"] = { ref: X.utils.encode_range({ s: { r: 0, c: 0 }, e: { r: Math.max(h.filas.length, 1), c: h.columnas.length - 1 } }) };
      h.columnas.forEach((c, j) => {
        const z = c[1] === "m" ? '"$"#,##0' : c[1] === "n" ? "#,##0" : c[1] === "p" ? "0.0%" : c[1] === "d" ? "#,##0.0" : null; if (!z) return;
        for (let i = 1; i <= h.filas.length; i++) { const cell = ws[X.utils.encode_cell({ r: i, c: j })]; if (cell && cell.t === "n") cell.z = z; }
      });
      let n = String(h.nombre).replace(/[\\/?*[\]:]/g, " ").slice(0, 31), k = 2;
      while (usados.has(n)) n = String(h.nombre).slice(0, 28) + " " + k++;
      usados.add(n); X.utils.book_append_sheet(wb, ws, n);
    });
    X.writeFile(wb, slug(V.titulo) + ".xlsx");
  }

  function aPdf(V) {
    const { jsPDF } = window.jspdf, doc = new jsPDF({ orientation: "landscape", unit: "pt", format: "a4" });
    const W = doc.internal.pageSize.getWidth(), H = doc.internal.pageSize.getHeight();
    doc.setFillColor(21, 11, 61); doc.rect(0, 0, W, 64, "F");
    doc.setTextColor(255, 255, 255); doc.setFont("helvetica", "bold"); doc.setFontSize(15); doc.text("X-irin Technologies S.A.S.", 32, 28);
    doc.setFont("helvetica", "normal"); doc.setFontSize(9); doc.setTextColor(180, 166, 219); doc.text("Estrategia Electoral 2027 · Generado " + ahora(), 32, 46);
    doc.setTextColor(21, 11, 61); doc.setFont("helvetica", "bold"); doc.setFontSize(14);
    const t = doc.splitTextToSize(V.titulo, W - 64); doc.text(t, 32, 92);
    doc.setFont("helvetica", "normal"); doc.setFontSize(9); doc.setTextColor(92, 79, 130);
    const st = doc.splitTextToSize(V.subtitulo || "", W - 64); doc.text(st, 32, 92 + t.length * 16);
    let y = 110 + t.length * 16 + st.length * 11;
    V.hojas.forEach(h => {
      if (y > H - 120) { doc.addPage(); y = 48; }
      doc.setFont("helvetica", "bold"); doc.setFontSize(11); doc.setTextColor(21, 11, 61); doc.text(h.nombre + " (" + h.filas.length + ")", 32, y);
      const cols = h.columnas.map((c, j) => [c, j]).filter(([c]) => !c[3]);
      const ancho = c => Math.max(c[2] || 12, c[1] === "f" ? 13 : 8);
      const tot = cols.reduce((s, [c]) => s + ancho(c), 0), fs = cols.length > 12 ? 6.5 : 7.5;
      doc.autoTable({ startY: y + 8, margin: { left: 32, right: 32, bottom: 40 }, head: [cols.map(([c]) => c[0])],
        body: h.filas.length ? h.filas.map(f => cols.map(([c, j]) => { const v = fmt(limpio(f[j]), c[1]); return v.length > 200 ? v.slice(0, 200) + "…" : v; }))
          : [[{ content: "Sin registros.", colSpan: cols.length }]],
        styles: { font: "helvetica", fontSize: fs, cellPadding: 3, overflow: "linebreak", textColor: [21, 11, 61], lineColor: [224, 217, 247], lineWidth: 0.5 },
        headStyles: { fillColor: [21, 11, 61], textColor: [255, 255, 255], fontStyle: "bold", fontSize: fs }, alternateRowStyles: { fillColor: [248, 246, 255] },
        columnStyles: Object.fromEntries(cols.map(([c], k) => [k, Object.assign({ cellWidth: ancho(c) / tot * (W - 64) },
          /[mnpd]/.test(c[1]) ? { halign: "right" } : {})])) });
      y = doc.lastAutoTable.finalY + 26;
    });
    const n = doc.getNumberOfPages();
    for (let i = 1; i <= n; i++) {
      doc.setPage(i); doc.setFontSize(7); doc.setTextColor(92, 79, 130);
      doc.text("Fuentes: SECOP, RUES, SIRI y Boletín de Responsables Fiscales (datos.gov.co). " + AVISO, 32, H - 18);
      doc.text("Página " + i + " de " + n, W - 32, H - 18, { align: "right" });
    }
    doc.save(slug(V.titulo) + ".pdf");
  }

  function aCsv(V) {
    const q = v => '"' + String(v == null ? "" : v).replace(/"/g, '""') + '"';
    const hojas = V.hojas.filter(h => h.filas.length || V.hojas.length === 1);
    hojas.forEach((h, i) => setTimeout(() => descargar(new Blob(["﻿" + h.columnas.map(c => q(c[0])).join(";") + "\n" +
      h.filas.map(f => f.map((x, j) => h.columnas[j][1] === "p" && x !== "" && x != null ? q((x * 100).toFixed(1).replace(".", ",")) : q(limpio(x))).join(";")).join("\n")],
      { type: "text/csv;charset=utf-8" }), slug(V.titulo + (hojas.length > 1 ? " " + h.nombre : "")) + ".csv"), i * 500));
  }

  async function exportar(clave, formato, btn) {
    const txt = btn ? btn.textContent : ""; if (btn) { btn.disabled = true; btn.textContent = "Generando…"; }
    let V = null;
    try { V = vistas[clave] && await vistas[clave](); } catch (e) { V = null; }
    if (!V || !V.hojas || !V.hojas.some(h => h.filas.length)) {
      if (btn) { btn.disabled = false; btn.textContent = txt; }
      alert("Todavía no hay datos para exportar aquí."); return; }
    try {
      if (formato === "xlsx") { await cargarLib("xlsx"); aExcel(V); }
      else if (formato === "pdf") { await cargarLib("pdf"); aPdf(V); }
      else aCsv(V);
    } catch (e) { alert("No se pudo generar el archivo: " + e.message); }
    finally { if (btn) { btn.disabled = false; btn.textContent = txt; } }
  }

  const css = document.createElement("style");
  css.textContent = ".xexp{display:inline-flex;gap:6px;flex-wrap:wrap;align-items:center}.xexp small{font-size:12px;color:#5C4F82;font-weight:600;margin-right:2px}" +
    ".xexp button{background:#fff;color:#150B3D;border:1.5px solid #E0D9F7;border-radius:8px;padding:7px 12px;font:600 12.5px Inter,'Segoe UI',sans-serif;cursor:pointer}" +
    ".xexp button:hover{border-color:#FFB020}.xexp button:disabled{opacity:.5;cursor:default}";
  document.head.appendChild(css);
  document.addEventListener("click", e => { const b = e.target.closest("[data-xexp]"); if (b) { e.preventDefault(); e.stopPropagation(); exportar(b.dataset.xexp, b.dataset.f, b); } }, true);

  window.XEXP = {
    registrar: (clave, fn) => { vistas[clave] = fn; },
    botones: (clave, etiqueta) => '<span class="xexp">' + (etiqueta ? "<small>" + etiqueta + "</small>" : "") +
      ["xlsx:Excel", "pdf:PDF", "csv:CSV"].map(x => { const [f, t] = x.split(":"); return '<button type="button" data-xexp="' + clave + '" data-f="' + f + '">' + t + "</button>"; }).join("") + "</span>",
    exportar
  };
})();
