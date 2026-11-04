(() => {
  const events = window.BBH_EVENTS || [];
  const select = document.querySelector('#event');
  const image = document.querySelector('#corner');
  const previous = document.querySelector('#previous');
  const next = document.querySelector('#next');
  if (!events.length) { document.querySelector('#summary').textContent = 'Plot data have not been generated yet.'; return; }
  const number = new Intl.NumberFormat('en-US');
  const duration = (s) => s >= 3600 ? `${(s / 3600).toFixed(2)} h` : `${(s / 60).toFixed(1)} min`;
  events.forEach((event) => { const option = document.createElement('option'); option.value = event.id; option.textContent = String(event.id).padStart(3, '0'); select.append(option); });
  function render(id) {
    const event = events.find((e) => e.id === id) || events[0];
    select.value = event.id;
    previous.disabled = event.id === events[0].id; next.disabled = event.id === events[events.length - 1].id;
    const label = String(event.id).padStart(3, '0');
    document.querySelector('#summary').textContent = `Injection ${label} · matched likelihood · ${events.length} available comparisons · reference is nlive=2000`;
    document.querySelector('#table-caption').textContent = `Injection ${label}: sampler settings and retained samples`;
    const body = document.querySelector('#metrics'); body.replaceChildren();
    [['Cheap', event.cheap, 'cheap'], ['Reference', event.reference, 'reference']].forEach(([name, run, style]) => {
      const row = document.createElement('tr');
      [name, number.format(run.nlive), `${number.format(run.rows)} / ${number.format(run.original_rows)}`, `${run.log_evidence.toFixed(3)} ± ${run.log_evidence_err.toFixed(3)}`, duration(run.seconds)].forEach((value, index) => { const cell = document.createElement(index === 0 ? 'th' : 'td'); if (index === 0) { cell.scope = 'row'; cell.className = style; } cell.textContent = value; row.append(cell); }); body.append(row);
    });
    document.querySelector('#plot-error').hidden = true; image.hidden = false;
    image.alt = `Corner plot for injection ${label}: cheap Dynesty 100 live points and reference Dynesty 2000 live points, using eight shared intrinsic parameters.`;
    image.src = event.plot; document.querySelector('#open-plot').href = event.plot;
    document.querySelector('#audit').textContent = `This event: maximum likelihood replay residual ${event.audit.max_abs_log_likelihood_residual.toExponential(2)}; prior residual ${event.audit.max_abs_log_prior_residual.toExponential(2)}. Likelihood identity: ${event.likelihood_id}.`;
    history.replaceState(null, '', `#event=${event.id}`);
  }
  image.addEventListener('error', () => { image.hidden = true; document.querySelector('#plot-error').hidden = false; });
  select.addEventListener('change', () => render(Number(select.value)));
  previous.addEventListener('click', () => render(Number(select.value) - 1));
  next.addEventListener('click', () => render(Number(select.value) + 1));
  window.addEventListener('hashchange', () => render(Number(new URLSearchParams(location.hash.slice(1)).get('event') || 0)));
  render(Number(new URLSearchParams(location.hash.slice(1)).get('event') || 0));
})();
