(() => {
  const $ = (selector) => document.querySelector(selector);
  const ns = 'http://www.w3.org/2000/svg';
  const colors = {cheap: '#2166ac', nismo: '#28814c'};
  let data = window.BBH_MAIN_RESULTS;
  let activeDataset = 'main_results';
  const value = (x, digits=4) => Number.isFinite(x) ? x.toFixed(digits) : '—';
  const estimate = (x, error) => Number.isFinite(x) ? `${value(x, 3)} ± ${value(error, 3)}` : '—';
  const svgNode = (tag, attrs={}, text) => {
    const node = document.createElementNS(ns, tag);
    Object.entries(attrs).forEach(([name, val]) => node.setAttribute(name, val));
    if (text !== undefined) node.textContent = text;
    return node;
  };
  function chart(kind) {
    const parameter = $('#jsd-parameter').value;
    const series = [];
    data.events.forEach((event) => ['cheap', 'nismo'].forEach((method) => {
      let y, error=0;
      if (kind === 'evidence') {
        y = event[`delta_lnz_${method}_reference`];
        error = event[`delta_lnz_${method}_reference_error`];
      } else {
        y = parameter === 'mean' ? event[`jsd_${method}_reference_bits`] : event.jsd_marginals[parameter][`${method}_reference_bits`];
      }
      if (Number.isFinite(y)) series.push({id: event.event_id, method, y, error});
    }));
    const width=1100, height=300, margin={left:70, right:25, top:22, bottom:50};
    let low = kind === 'evidence' ? Math.min(0, ...series.map(p => p.y-p.error)) : 0;
    let high = Math.max(kind === 'evidence' ? 0 : .02, ...series.map(p => p.y+p.error));
    const padding=(high-low)*.08 || .05;
    if (kind === 'evidence') low -= padding;
    high += padding;
    const x = (id) => margin.left+(id+1)/101*(width-margin.left-margin.right);
    const y = (v) => height-margin.bottom-(v-low)/(high-low)*(height-margin.top-margin.bottom);
    const title = kind === 'evidence' ? 'Evidence differences from the 2,000-live reference' : `Posterior JSD: ${parameter === 'mean' ? 'mean of eight marginals' : parameter}`;
    const svg=svgNode('svg', {viewBox:`0 0 ${width} ${height}`, role:'img', 'aria-label':title});
    svg.append(svgNode('title', {}, title));
    for (let i=0; i<=4; i++) {
      const tick=low+(high-low)*i/4;
      svg.append(svgNode('line', {x1:margin.left, x2:width-margin.right, y1:y(tick), y2:y(tick), stroke:'#e4e7eb'}));
      svg.append(svgNode('text', {x:margin.left-10, y:y(tick)+4, 'text-anchor':'end', class:'chart-tick'}, value(tick, kind === 'evidence' ? 1 : 3)));
    }
    if (kind === 'evidence') svg.append(svgNode('line', {x1:margin.left, x2:width-margin.right, y1:y(0), y2:y(0), stroke:'#56606b', 'stroke-dasharray':'5 4'}));
    for (const id of [0,10,20,30,40,50,60,70,80,90,99]) svg.append(svgNode('text', {x:x(id), y:height-28, 'text-anchor':'middle', class:'chart-tick'}, id));
    svg.append(svgNode('text', {x:(width+margin.left-margin.right)/2, y:height-5, 'text-anchor':'middle', class:'chart-label'}, 'Injection ID'));
    svg.append(svgNode('text', {transform:`translate(18 ${(height-margin.bottom+margin.top)/2}) rotate(-90)`, 'text-anchor':'middle', class:'chart-label'}, kind === 'evidence' ? 'ΔlnZ' : 'JSD [bits]'));
    series.forEach(point => {
      const px=x(point.id)+(point.method === 'cheap' ? -1.5 : 1.5), py=y(point.y);
      const link=svgNode('a', {href:`#event=${point.id}`, 'aria-label':`Injection ${point.id}, ${point.method}: ${value(point.y)}${kind === 'evidence' ? ` ± ${value(point.error)}` : ' bits'}`, tabindex:'0'});
      link.append(svgNode('title', {}, `Injection ${point.id} · ${point.method} · ${value(point.y)}${kind === 'evidence' ? ` ± ${value(point.error)}` : ' bits'}`));
      if (kind === 'evidence') link.append(svgNode('line', {x1:px,x2:px,y1:y(point.y-point.error),y2:y(point.y+point.error),stroke:colors[point.method], 'stroke-opacity':'.55'}));
      link.append(point.method === 'cheap' ? svgNode('circle', {cx:px,cy:py,r:3,fill:colors.cheap}) : svgNode('path', {d:`M ${px} ${py-4} l 4 4 -4 4 -4 -4 Z`,fill:'white',stroke:colors.nismo,'stroke-width':1.5}));
      svg.append(link);
    });
    $(`#${kind === 'evidence' ? 'evidence' : 'jsd'}-chart`).replaceChildren(svg);
  }
  function table() {
    const body=$('#main-result-rows'); body.replaceChildren();
    const rows=data.events.filter(row => !$('#completed-only').checked || row.nis_status === 'converged');
    $('#main-table-caption').textContent = `${rows.length} injections shown · JSD columns are means across eight marginals [bits]`;
    rows.forEach(row => {
      const tr=document.createElement('tr');
      const first=document.createElement('th'); first.scope='row';
      const link=document.createElement('a'); link.href=`#event=${row.event_id}`; link.textContent=String(row.event_id).padStart(3,'0'); first.append(link); tr.append(first);
      const alert=Object.values(row.posterior_diagnostic_flags||{}).some(Boolean);
      const values=[estimate(row.lnz_reference,row.lnz_reference_error), estimate(row.delta_lnz_cheap_reference,row.delta_lnz_cheap_reference_error), estimate(row.delta_lnz_nismo_reference,row.delta_lnz_nismo_reference_error), value(row.jsd_cheap_reference_bits), value(row.jsd_nismo_reference_bits), row.nis_status === 'converged' ? `Stopping threshold reached${alert?' · diagnostic alert':''}` : row.nis_status.replaceAll('_',' ')];
      values.forEach(text => { const td=document.createElement('td'); td.textContent=text; tr.append(td); });
      body.append(tr);
    });
  }
  function render() {
    if (!data || data.schema_version !== 1) { $('#main-status').textContent='The main comparison snapshot is not available.'; return; }
    window.BBH_MAIN_RESULTS=data;
    const count=data.nis_counts.converged || 0;
    $('#main-status').textContent=`${count}/${data.event_count} NISMO comparisons available · campaign ${data.campaign_state}${Number.isInteger(data.active_event)?` · running injection ${data.active_event}`:''} · snapshot ${new Date(data.created_utc).toLocaleString()}. Missing results are not zero.`;
    $('#campaign-settings').textContent=data.campaign_metadata?.description || 'Original exploratory campaign: bandwidth scale 1, local walks and heuristic recovery. See the sampling diagnostics before interpreting these results.';
    $('#results-csv').href=`data/${activeDataset}.csv`;
    $('#results-json').href=`data/${activeDataset}.json`;
    const paired=data.paired_summary;
    $('#paired-summary').textContent=paired.events ? `On the same ${paired.events} completed events: mean marginal JSD is ${value(paired.mean_jsd_cheap_bits)} bits for cheap and ${value(paired.mean_jsd_nismo_bits)} bits for NISMO. Median |ΔlnZ| is ${value(paired.median_abs_delta_cheap,3)} and ${value(paired.median_abs_delta_nismo,3)}, respectively.` : 'Paired aggregates will appear as NISMO results become available.';
    chart('evidence'); chart('jsd'); table();
    window.dispatchEvent(new Event('bbh-main-results-updated'));
  }
  const names=['chirp_mass','mass_ratio','a_1','a_2','tilt_1','tilt_2','phi_12','phi_jl'];
  names.forEach(name => {const option=document.createElement('option');option.value=name;option.textContent=name;$('#jsd-parameter').append(option);});
  $('#jsd-parameter').addEventListener('change', () => chart('jsd'));
  $('#completed-only').addEventListener('change', table);
  async function loadSnapshot(dataset) {
    const button=$('#refresh-results'), select=$('#campaign-select');button.disabled=true;select.disabled=true;
    try {const response=await fetch(`data/${dataset}.json?t=${Date.now()}`,{cache:'no-store'});if(!response.ok)throw new Error(`HTTP ${response.status}`);const next=await response.json();if(next.schema_version!==1||!Array.isArray(next.events))throw new Error('Invalid snapshot');data=next;activeDataset=dataset;select.value=dataset;render();}
    catch(error) {select.value=activeDataset;$('#main-status').textContent=`Refresh unavailable (${error.message}). The existing snapshot remains displayed.`;}
    finally {button.disabled=false;select.disabled=false;}
  }
  $('#refresh-results').addEventListener('click', () => loadSnapshot(activeDataset));
  $('#campaign-select').addEventListener('change', () => loadSnapshot($('#campaign-select').value));
  render();
})();
