// Widget Modal - Análisis de Impacto Petro
(function() {
  // CSS para el modal
  const css = `
    #analisis-modal {
      display: none;
      position: fixed;
      z-index: 9999;
      left: 0;
      top: 0;
      width: 100%;
      height: 100%;
      background-color: rgba(0,0,0,0.5);
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    }
    #analisis-modal.show {
      display: flex;
      align-items: center;
      justify-content: center;
    }
    .analisis-content {
      background-color: white;
      padding: 30px;
      border-radius: 8px;
      max-width: 600px;
      width: 90%;
      max-height: 80vh;
      overflow-y: auto;
      box-shadow: 0 4px 20px rgba(0,0,0,0.3);
    }
    .analisis-content h2 {
      color: #1a1a1a;
      margin-top: 0;
      border-bottom: 3px solid #ff9800;
      padding-bottom: 10px;
    }
    .analisis-stat {
      display: grid;
      grid-template-columns: 1fr 1fr 1fr;
      gap: 15px;
      margin: 20px 0;
    }
    .stat-box {
      background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
      color: white;
      padding: 20px;
      border-radius: 6px;
      text-align: center;
    }
    .stat-box.izquierda { 
      background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%); 
    }
    .stat-box.derecha { 
      background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%); 
    }
    .stat-box.centro { 
      background: linear-gradient(135deg, #43e97b 0%, #38f9d7 100%); 
    }
    .stat-box h3 { 
      margin: 0; 
      font-size: 12px; 
      opacity: 0.9; 
    }
    .stat-box .valor { 
      font-size: 32px; 
      font-weight: bold; 
      margin: 10px 0; 
    }
    .stat-box .label { 
      font-size: 11px; 
      opacity: 0.8; 
    }
    .analisis-texto {
      background: #f5f5f5;
      padding: 15px;
      border-left: 4px solid #ff9800;
      margin: 20px 0;
      line-height: 1.6;
      font-size: 14px;
    }
    .close-btn {
      background: #ff9800;
      color: white;
      border: none;
      padding: 10px 20px;
      border-radius: 4px;
      cursor: pointer;
      margin-top: 20px;
      width: 100%;
      font-size: 14px;
      font-weight: bold;
    }
    .close-btn:hover {
      background: #e68900;
    }
    #analisis-trigger {
      position: fixed;
      bottom: 30px;
      right: 30px;
      z-index: 9998;
      background: #ff9800;
      color: white;
      border: none;
      padding: 15px 25px;
      border-radius: 50px;
      cursor: pointer;
      font-weight: bold;
      box-shadow: 0 4px 12px rgba(0,0,0,0.3);
      transition: all 0.3s ease;
    }
    #analisis-trigger:hover {
      background: #e68900;
      transform: scale(1.05);
    }
  `;

  // HTML del modal
  const html = `
    <button id="analisis-trigger">📊 Análisis Petro</button>
    <div id="analisis-modal">
      <div class="analisis-content">
        <h2>Impacto del Gobierno Petro 2023→2026</h2>
        
        <h3>Bogotá - Concejo 2023 (Gobierno Santos)</h3>
        <div class="analisis-stat">
          <div class="stat-box izquierda">
            <h3>Izquierda</h3>
            <div class="valor">1.2%</div>
          </div>
          <div class="stat-box derecha">
            <h3>Derecha</h3>
            <div class="valor">9.8%</div>
          </div>
          <div class="stat-box centro">
            <h3>Centro</h3>
            <div class="valor">37.8%</div>
          </div>
        </div>

        <h3>Bogotá - Congreso 2026 (Gobierno Petro)</h3>
        <div class="analisis-stat">
          <div class="stat-box izquierda">
            <h3>Izquierda</h3>
            <div class="valor">42.3%</div>
          </div>
          <div class="stat-box derecha">
            <h3>Derecha</h3>
            <div class="valor">7.0%</div>
          </div>
          <div class="stat-box centro">
            <h3>Centro</h3>
            <div class="valor">20.6%</div>
          </div>
        </div>

        <h3>Cambio Electoral (2023→2026)</h3>
        <div class="analisis-stat">
          <div class="stat-box izquierda">
            <h3>Δ Izquierda</h3>
            <div class="valor">+41.1pp</div>
          </div>
          <div class="stat-box derecha">
            <h3>Δ Derecha</h3>
            <div class="valor">-2.8pp</div>
          </div>
          <div class="stat-box centro">
            <h3>Δ Centro</h3>
            <div class="valor">-17.2pp</div>
          </div>
        </div>

        <div class="analisis-texto">
          <strong>🔍 Interpretación:</strong> Petro multiplicó por 40x el voto de izquierda en Bogotá (1-2% a 42%). Cambio masivo pero atomizado en múltiples partidos. Centro perdió 17 puntos porcentuales. Fenómeno urbano: Bogotá 42% vs Cundinamarca 15%.
        </div>

        <button class="close-btn">Cerrar</button>
      </div>
    </div>
  `;

  // Inyectar cuando el DOM esté listo
  document.addEventListener('DOMContentLoaded', function() {
    // Agregar CSS
    const style = document.createElement('style');
    style.textContent = css;
    document.head.appendChild(style);

    // Agregar HTML
    const container = document.createElement('div');
    container.innerHTML = html;
    document.body.appendChild(container);

    // Event listeners
    const modal = document.getElementById('analisis-modal');
    const trigger = document.getElementById('analisis-trigger');
    const closeBtn = document.querySelector('.close-btn');

    trigger.addEventListener('click', () => {
      modal.classList.add('show');
    });

    closeBtn.addEventListener('click', () => {
      modal.classList.remove('show');
    });

    modal.addEventListener('click', (e) => {
      if (e.target === modal) {
        modal.classList.remove('show');
      }
    });
  });
})();