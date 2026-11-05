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
    const main = window.BBH_MAIN_RESULTS?.events.find((row) => row.event_id === event.id);
    document.querySelector('#summary').textContent = `Injection ${label} · matched likelihood · ${events.length} available comparisons · reference is nlive=2000`;
    document.querySelector('#table-caption').textContent = `Injection ${label}: sampler settings and retained samples`;
    const body = document.querySelector('#metrics'); body.replaceChildren();
    const runs=[['Cheap', event.cheap, 'cheap'], ['Reference', event.reference, 'reference']];
    if(main?.nis_status === 'converged') runs.push(['NISMO', {nlive:main.nis_nlive,rows:main.nis_weighted_rows,original_rows:main.nis_weighted_rows,log_evidence:main.nis_log_evidence,log_evidence_err:main.nis_log_evidence_error,seconds:main.nis_sampler_seconds},'nismo']);
    runs.forEach(([name, run, style]) => {
      const row = document.createElement('tr');
      [name, number.format(run.nlive), `${number.format(run.rows)} / ${number.format(run.original_rows)}`, `${run.log_evidence.toFixed(3)} ± ${run.log_evidence_err.toFixed(3)}`, duration(run.seconds)].forEach((value, index) => { const cell = document.createElement(index === 0 ? 'th' : 'td'); if (index === 0) { cell.scope = 'row'; cell.className = style; } cell.textContent = value; row.append(cell); }); body.append(row);
    });
    document.querySelector('#plot-error').hidden = true; image.hidden = false;
    const plot=main?.nis_plot || event.plot;
    image.alt = `Corner plot for injection ${label}: cheap Dynesty, reference Dynesty and ${main?.nis_plot ? 'weighted NISMO' : 'available baseline'} posteriors, using eight shared intrinsic parameters.`;
    image.src = plot; document.querySelector('#open-plot').href = plot;
    document.querySelector('#plot-caption').textContent=`Blue solid: cheap; orange dashed: reference; ${main?.nis_plot ? 'green dotted: weighted NISMO; ' : ''}gray: injection truth. Contours enclose 50% and 90% probability; diagonal densities are normalized separately. Angles are in radians. ${main?.nis_plot ? 'NISMO uses original frozen event-0 data or explicitly validated local reconstructions for other events.' : 'NISMO output is not available in this snapshot.'}`;
    const marginal=document.querySelector('#marginal-jsd');marginal.replaceChildren();
    if(main){
      Object.entries(main.jsd_marginals).forEach(([name,values])=>{const row=document.createElement('tr');[name,values.cheap_reference_bits,values.nismo_reference_bits].forEach((value,i)=>{const cell=document.createElement(i===0?'th':'td');if(i===0)cell.scope='row';cell.textContent=typeof value==='string'?value:Number.isFinite(value)?value.toFixed(4):'—';row.append(cell);});marginal.append(row);});
      const calibration=main.reference_split_calibration;
      document.querySelector('#event-main-summary').textContent=`Mean marginal JSD: cheap ${main.jsd_cheap_reference_bits.toFixed(4)} bits; NISMO ${Number.isFinite(main.jsd_nismo_reference_bits)?main.jsd_nismo_reference_bits.toFixed(4):'not available'}${Number.isFinite(main.jsd_nismo_reference_bits)?' bits':''}. Reference-split calibration for ${main.cheap_rows} cheap draws: median ${calibration.median_bits.toFixed(4)} bits, 5–95% range ${calibration.p05_bits.toFixed(4)}–${calibration.p95_bits.toFixed(4)}. ${main.nis_status==='converged'?`NISMO has ${main.nis_weighted_rows} weighted points, weight ESS ${main.nis_weight_ess.toFixed(0)} and ${main.nis_recovery_iterations} recovery iterations.`:''}`;
    }
    document.querySelector('#audit').textContent = `This event: maximum likelihood replay residual ${event.audit.max_abs_log_likelihood_residual.toExponential(2)}; prior residual ${event.audit.max_abs_log_prior_residual.toExponential(2)}. Likelihood identity: ${event.likelihood_id}.`;
    history.replaceState(null, '', `#event=${event.id}`);
  }
  image.addEventListener('error', () => { image.hidden = true; document.querySelector('#plot-error').hidden = false; });
  select.addEventListener('change', () => render(Number(select.value)));
  previous.addEventListener('click', () => render(Number(select.value) - 1));
  next.addEventListener('click', () => render(Number(select.value) + 1));
  window.addEventListener('hashchange', () => render(Number(new URLSearchParams(location.hash.slice(1)).get('event') || 0)));
  window.addEventListener('bbh-main-results-updated', () => render(Number(select.value)));
  render(Number(new URLSearchParams(location.hash.slice(1)).get('event') || 0));
})();
