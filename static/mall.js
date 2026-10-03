document.addEventListener('DOMContentLoaded', () => {
  // ========================================================
  // ANIMACIÓN DECORATIVA DE GRÚA
  // La estructura queda fija y solo el cable sigue el scroll;
  // CSS elimina toda la grúa en pantallas móviles.
  // ========================================================
  const cable = document.querySelector('#crane-cable');
  if (cable && matchMedia('(min-width: 901px)').matches) {
    let scheduled = false;
    const updateCrane = () => {
      const progress = Math.min(1, scrollY / Math.max(1, document.documentElement.scrollHeight - innerHeight));
      cable.style.height = `${95 + progress * 190}px`;
      scheduled = false;
    };
    addEventListener('scroll', () => {
      if (!scheduled) { requestAnimationFrame(updateCrane); scheduled = true; }
    }, { passive: true });
    updateCrane();
  }

  // ========================================================
  // ASISTENCIA DE FECHAS EN EL CARRO
  // Limita el selector visual y mantiene fin posterior a inicio.
  // La validación definitiva se repite siempre en Django.
  // ========================================================
  const tomorrowDate = new Date();
  tomorrowDate.setDate(tomorrowDate.getDate() + 1);
  const tomorrow = `${tomorrowDate.getFullYear()}-${String(tomorrowDate.getMonth() + 1).padStart(2, '0')}-${String(tomorrowDate.getDate()).padStart(2, '0')}`;
  document.querySelectorAll('input[name="fecha_inicio"]').forEach(start => {
    const form = start.closest('form');
    const end = form?.querySelector('input[name="fecha_fin"]');
    start.min = tomorrow;
    if (end) {
      end.min = tomorrow;
      start.addEventListener('change', () => {
        const next = new Date(`${start.value}T12:00:00`);
        next.setDate(next.getDate() + 1);
        end.min = next.toISOString().slice(0, 10);
        if (end.value && end.value <= start.value) end.value = '';
      });
    }
  });

  // ========================================================
  // VISTA PREVIA DEL PRECIO
  // Replica semanas, días y garantía para respuesta inmediata;
  // Django es la fuente de verdad y persiste al guardar.
  // ========================================================
  const money = new Intl.NumberFormat('es-CL', { maximumFractionDigits: 0 });
  const cartItems = [...document.querySelectorAll('.cart-edit-item')];
  const updateTotal = () => {
    const total = cartItems.reduce((sum, item) => sum + Number(item.querySelector('.preview-subtotal')?.dataset.value || 0), 0);
    const target = document.querySelector('#cart-total');
    if (target) target.textContent = money.format(total);
  };
  cartItems.forEach(item => {
    const form = item.querySelector('.cart-edit-form');
    const subtotal = item.querySelector('.preview-subtotal');
    if (!form || !subtotal) return;
    subtotal.dataset.value = item.dataset.currentSubtotal || '0';
    const recalculate = () => {
      const start = form.elements.fecha_inicio.value;
      const end = form.elements.fecha_fin.value;
      const quantity = Math.max(1, Number(form.elements.cantidad.value || 1));
      const detail = item.querySelector('.price-breakdown');
      const days = start && end ? Math.round((new Date(`${end}T00:00:00Z`) - new Date(`${start}T00:00:00Z`)) / 86400000) : 0;
      if (days <= 0) {
        detail.classList.add('invalid-dates');
        detail.innerHTML = '<span>Selecciona fechas válidas para calcular el arriendo.</span>';
        subtotal.dataset.value = '0';
        subtotal.textContent = '0';
        updateTotal();
        return;
      }
      const weeks = Math.floor(days / 7);
      const rest = days % 7;
      const rental = (weeks * Number(item.dataset.weekly) + rest * Number(item.dataset.daily)) * quantity;
      const guarantee = Number(item.dataset.guarantee) * quantity;
      const value = rental + guarantee;
      detail.classList.remove('invalid-dates');
      detail.innerHTML = `<span><b>${days}</b> días: <b>${weeks}</b> semana(s) a $${money.format(item.dataset.weekly)} + <b>${rest}</b> día(s) a $${money.format(item.dataset.daily)}</span><span>Arriendo: $<b>${money.format(rental)}</b> · Garantía: $${money.format(guarantee)}</span>`;
      subtotal.dataset.value = String(value);
      subtotal.textContent = money.format(value);
      updateTotal();
    };
    form.querySelectorAll('input').forEach(input => input.addEventListener('input', recalculate));
  });
  updateTotal();
});
