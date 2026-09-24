// Interacción de la página de partidos: abrir mercados, elegir cuota y unidades.
// Ojo: la cuota que se ve aquí es solo informativa. Al confirmar, el servidor
// toma la cuota vigente en ese instante.
(function () {
  const boleta = document.getElementById('boleta');
  if (!boleta) return;

  const $ = (sel) => boleta.querySelector(sel);
  const rango = $('[name=unidades]');
  const confirmar = $('[data-confirmar]');
  const aviso = document.querySelector('[data-aviso]');
  let seleccion = null;

  // ---- Abrir / cerrar los mercados adicionales de un partido ----
  document.querySelectorAll('.partido-equipos').forEach((boton) => {
    boton.addEventListener('click', () => {
      const abierto = boton.getAttribute('aria-expanded') === 'true';
      boton.setAttribute('aria-expanded', String(!abierto));
      document.getElementById(boton.getAttribute('aria-controls')).hidden = abierto;
      const texto = boton.querySelector('[data-texto-cerrado]');
      texto.textContent = abierto ? texto.dataset.textoCerrado : texto.dataset.textoAbierto;
    });
  });

  // ---- Elegir una cuota ----
  function seleccionar(datos) {
    seleccion = datos;
    $('[name=opcion]').value = datos.opcion;
    $('[name=cuota_vista]').value = datos.cuota;
    $('[data-cuando]').textContent = datos.cuando;
    $('[data-partido]').textContent = datos.partido;
    $('[data-etiqueta]').textContent = datos.etiqueta;
    $('[data-cuota]').textContent = Number(datos.cuota).toFixed(2);
    $('[data-seleccion]').hidden = false;
    $('[data-vacia]').hidden = true;
    if (confirmar) confirmar.disabled = false;
    document.querySelectorAll('button.cuota').forEach((b) => {
      b.setAttribute('aria-pressed', String(b.dataset.opcion === String(datos.opcion)));
    });
    if (aviso) aviso.querySelector('[data-aviso-texto]').textContent =
      datos.etiqueta + ' · ' + Number(datos.cuota).toFixed(2);
    actualizar();
  }

  document.addEventListener('click', (e) => {
    const boton = e.target.closest('button.cuota');
    if (boton && !boton.disabled) seleccionar(boton.dataset);
  });

  // ---- Unidades y resumen ----
  function actualizar() {
    const u = Number(rango.value);
    $('[data-unidades]').textContent = u;
    $('[data-restar]').disabled = u <= 1;
    $('[data-sumar]').disabled = u >= 10;
    $('[data-si-pierde]').textContent = '−' + u + ' u';
    $('[data-si-gana]').textContent = seleccion
      ? '+' + (u * (Number(seleccion.cuota) - 1)).toFixed(2) + ' u'
      : '—';
    mostrarAviso();
  }

  function cambiar(delta) {
    rango.value = Math.min(10, Math.max(1, Number(rango.value) + delta));
    actualizar();
  }
  $('[data-restar]').addEventListener('click', () => cambiar(-1));
  $('[data-sumar]').addEventListener('click', () => cambiar(1));
  rango.addEventListener('input', actualizar);

  // Evita doble envío si alguien hace doble clic en "Confirmar"
  boleta.addEventListener('submit', () => { if (confirmar) confirmar.disabled = true; });

  // ---- En celular: barra inferior que lleva a la boleta ----
  let boletaVisible = false;
  function mostrarAviso() {
    if (!aviso) return;
    const celular = window.matchMedia('(max-width: 1000px)').matches;
    aviso.hidden = !(seleccion && celular && !boletaVisible);
  }
  if ('IntersectionObserver' in window) {
    new IntersectionObserver((entradas) => {
      boletaVisible = entradas[0].isIntersecting;
      mostrarAviso();
    }).observe(boleta);
  }
  window.addEventListener('resize', mostrarAviso);

  // Selección que viene desde el servidor (p. ej. al volver tras un error)
  const inicial = JSON.parse(document.getElementById('seleccion-inicial').textContent);
  if (inicial) seleccionar(inicial);
  actualizar();
})();
