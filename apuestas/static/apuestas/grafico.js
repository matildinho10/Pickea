// Gráfico de unidades acumuladas: línea vertical + recuadro que siguen al mouse
// (o a las flechas del teclado) y se ajustan al partido más cercano.
(function () {
  const area = document.querySelector('.grafico-area');
  const fuente = document.getElementById('datos-grafico');
  if (!area || !fuente) return;

  const datos = JSON.parse(fuente.textContent);
  const cruz = area.querySelector('[data-cruz]');
  const punto = area.querySelector('[data-punto]');
  const tip = area.querySelector('[data-tooltip]');
  let actual = null;

  const signo = (v, d) => (v > 0 ? '+' : v < 0 ? '−' : '') + Math.abs(v).toFixed(d);

  function mostrar(i) {
    actual = Math.max(0, Math.min(datos.length - 1, i));
    const d = datos[actual];
    cruz.style.left = d.x + '%';
    punto.style.left = d.x + '%';
    punto.style.top = d.y + '%';
    // Siempre con textContent: los nombres vienen de la base de datos
    tip.querySelector('[data-t-acum]').textContent = signo(d.a, 1) + ' u acumuladas';
    tip.querySelector('[data-t-partido]').textContent = d.partido;
    tip.querySelector('[data-t-detalle]').textContent =
      actual === 0 ? '' : d.fecha + ' · ' + signo(d.g, 2) + ' u en el partido';
    // El recuadro se pone al lado izquierdo si el punto está en la mitad derecha
    tip.classList.toggle('a-la-izquierda', d.x > 50);
    tip.style.left = d.x + '%';
    cruz.hidden = punto.hidden = tip.hidden = false;
  }

  function ocultar() {
    cruz.hidden = punto.hidden = tip.hidden = true;
  }

  area.addEventListener('pointermove', (e) => {
    const r = area.getBoundingClientRect();
    const fraccion = (e.clientX - r.left) / r.width;
    mostrar(Math.round(fraccion * (datos.length - 1)));
  });
  area.addEventListener('pointerleave', ocultar);

  area.addEventListener('focus', () => mostrar(actual ?? datos.length - 1));
  area.addEventListener('blur', ocultar);
  area.addEventListener('keydown', (e) => {
    const saltos = { ArrowLeft: -1, ArrowRight: 1, PageDown: -10, PageUp: 10 };
    if (e.key in saltos) { mostrar((actual ?? datos.length - 1) + saltos[e.key]); e.preventDefault(); }
    if (e.key === 'Home') { mostrar(0); e.preventDefault(); }
    if (e.key === 'End') { mostrar(datos.length - 1); e.preventDefault(); }
  });
})();
