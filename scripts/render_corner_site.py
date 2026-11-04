"""Render matched, source-checked corner overlays and a small static site dataset."""
import argparse,csv,gc,hashlib,io,json,math,zipfile
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.ticker import MaxNLocator
from scipy.ndimage import gaussian_filter1d
import numpy as np
import corner

parser=argparse.ArgumentParser()
parser.add_argument('cheap');parser.add_argument('reference');parser.add_argument('output')
parser.add_argument('--start',type=int,default=0);parser.add_argument('--stop',type=int,default=100)
args=parser.parse_args();out=Path(args.output);(out/'plots').mkdir(parents=True,exist_ok=True);(out/'data').mkdir(exist_ok=True)
keys=['chirp_mass','mass_ratio','a_1','a_2','tilt_1','tilt_2','phi_12','phi_jl']
labels=[r'$\mathcal{M}\ [M_\odot]$',r'$q$',r'$a_1$',r'$a_2$',r'$\theta_1\ [rad]$',r'$\theta_2\ [rad]$',r'$\phi_{12}\ [rad]$',r'$\phi_{JL}\ [rad]$']
blue='#2166ac';orange='#d97916'
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':9,'axes.labelsize':11,'xtick.labelsize':8,'ytick.labelsize':8,'axes.linewidth':0.7})
events=[]

def load_csv(data):
    r=list(csv.DictReader(io.StringIO(data.decode())))
    return np.asarray([[float(row[k]) for k in keys] for row in r])

with zipfile.ZipFile(args.cheap) as cz,zipfile.ZipFile(args.reference) as rz:
    cp=cz.namelist()[0].split('/')[0]+'/';rp=rz.namelist()[0].split('/')[0]+'/'
    for i in range(args.start,args.stop):
        d=f'events/injection_{i:03d}/'
        cb=cz.read(cp+d+'posterior.csv');rb=rz.read(rp+d+'posterior.csv')
        cs=json.loads(cz.read(cp+d+'summary.json'));rs=json.loads(rz.read(rp+d+'summary.json'))
        cm=json.loads(cz.read(cp+d+'strain_manifest.json'))
        assert cs['config']['sampler']=='dynesty' and cs['config']['kwargs']['nlive']==100
        assert rs['sampler']=='dynesty' and rs['sampler_kwargs']['nlive']==2000
        assert rs['comparison_audit']['passed']
        assert cs['likelihood_id']==rs['comparison_audit']['comparison_likelihood_id']==cm['likelihood_id']
        assert hashlib.sha256(cb).hexdigest()==cs['posterior_sha256']
        assert hashlib.sha256(rb).hexdigest()==rs['posterior_sha256']
        a=load_csv(cb);b=load_csv(rb)
        assert a.shape==(cs['posterior_rows'],8) and b.shape==(rs['posterior_rows'],8)
        assert np.isfinite(a).all() and np.isfinite(b).all()
        truth=[cm['scientific_config']['settings']['injection'][k] for k in keys]
        combined=np.concatenate([a,b]);ranges=[]
        bounds=[(14.,20.),(.125,1.),(0.,.99),(0.,.99),(0.,math.pi),(0.,math.pi),(0.,2*math.pi),(0.,2*math.pi)]
        for j,(low,high) in enumerate(bounds):
            lo=min(float(combined[:,j].min()),truth[j]);hi=max(float(combined[:,j].max()),truth[j]);pad=max((hi-lo)*.025,1e-8)
            ranges.append((low,high) if j>=6 else (max(low,lo-pad),min(high,hi+pad)))
        fig=plt.figure(figsize=(13.5,13.5))
        common=dict(bins=35,range=ranges,labels=labels,plot_datapoints=False,plot_density=False,fill_contours=False,levels=(.5,.9),smooth=1.0,smooth1d=1.0,max_n_ticks=3,show_titles=False,label_kwargs={'fontsize':11})
        corner.corner(b,fig=fig,color=orange,truths=truth,truth_color='#656b73',hist_kwargs={'linewidth':1.35,'linestyle':'--'},contour_kwargs={'linewidths':1.05,'linestyles':'--'},**common)
        corner.corner(a,fig=fig,color=blue,hist_kwargs={'linewidth':1.35},contour_kwargs={'linewidths':1.05},**common)
        axes=np.asarray(fig.axes).reshape(8,8);integrals=[]
        for j in range(8):
            ax=axes[j,j];ax.clear();edges=np.linspace(*ranges[j],36);centers=(edges[:-1]+edges[1:])/2;peaks=[];areas=[]
            for data,color,style in [(a,blue,'-'),(b,orange,'--')]:
                density,_=np.histogram(data[:,j],bins=edges,density=True);density=gaussian_filter1d(density,1.0)
                area=float(np.sum(density*np.diff(edges)));assert abs(area-1.0)<1e-8
                ax.plot(centers,density,color=color,ls=style,lw=1.35);peaks.append(float(density.max()));areas.append(area)
            ax.axvline(truth[j],color='#656b73',lw=.9);ax.set_xlim(ranges[j]);ax.set_ylim(0,max(peaks)*1.08);ax.set_yticks([]);ax.xaxis.set_major_locator(MaxNLocator(3,prune='both'))
            if j<7:ax.tick_params(labelbottom=False)
            else:ax.set_xlabel(labels[j],fontsize=11)
            integrals.append(areas)
        fig.subplots_adjust(top=.92,bottom=.075,left=.075,right=.98,hspace=.075,wspace=.075)
        fig.suptitle(f'Injection {i:03d} · Dynesty posterior comparison',x=.52,y=.985,fontsize=17)
        legend=[Line2D([],[],color=blue,lw=1.6,label=f'Cheap nlive=100 · {len(a):,} samples'),Line2D([],[],color=orange,lw=1.6,ls='--',label=f'Reference nlive=2000 · {len(b):,}/{rs["original_posterior_rows"]:,} samples'),Line2D([],[],color='#656b73',lw=1,label='Injection truth')]
        fig.legend(handles=legend,loc='upper center',bbox_to_anchor=(.52,.963),ncol=3,frameon=False,fontsize=10)
        fig.text(.52,.935,'Same axes and bins · separately normalized densities · 50% and 90% enclosed-probability contours',ha='center',fontsize=9,color='#49515b')
        filename=f'plots/injection_{i:03d}.png';path=out/filename
        fig.savefig(path,dpi=140,facecolor='white');plt.close(fig);gc.collect()
        event={'id':i,'plot':filename,'plot_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'matched':True,'likelihood_id':cs['likelihood_id'],'cheap':{'nlive':100,'rows':len(a),'original_rows':cs['original_posterior_rows'],'log_evidence':cs['log_evidence'],'log_evidence_err':cs['log_evidence_err'],'seconds':cs['sampling_seconds'],'seed':42},'reference':{'nlive':2000,'rows':len(b),'original_rows':rs['original_posterior_rows'],'log_evidence':rs['log_evidence'],'log_evidence_err':rs['log_evidence_err'],'seconds':rs['sampling_time'],'seed':None},'audit':rs['comparison_audit'],'source_hashes':{'cheap_posterior':hashlib.sha256(cb).hexdigest(),'reference_posterior':hashlib.sha256(rb).hexdigest(),'reference_original_result':rs['source_result_sha256']},'ranges':ranges,'parameters':keys,'diagonal_density_integrals':integrals}
        events.append(event)
        with (out/f'data/events_{args.start:03d}_{args.stop:03d}.json').open('w') as f:json.dump(events,f,separators=(',',':'))
        print(json.dumps({'event_id':i,'plot':str(path),'bytes':path.stat().st_size,'cheap_rows':len(a),'reference_rows':len(b)}),flush=True)
    metadata={'event_count':100,'matched_event_count':100,'cheap_archive_sha256':hashlib.sha256(Path(args.cheap).read_bytes()).hexdigest(),'reference_archive_sha256':hashlib.sha256(Path(args.reference).read_bytes()).hexdigest(),'parameters':keys,'contours':[.5,.9],'histogram_bins':35,'smoothing_bins':1.0,'reference_thinning':'up to 1000 uniform draws without replacement; selection seed 0; exact indices in reference archive','site_published':False}
    if args.start==0 and args.stop==100:
        metadata.update(cheap_retained_rows=sum(e['cheap']['rows'] for e in events),reference_retained_rows=sum(e['reference']['rows'] for e in events),reference_original_rows=sum(e['reference']['original_rows'] for e in events))
        (out/'data/events.js').write_text('window.BBH_EVENTS = '+json.dumps(events,separators=(',',':'))+';\n')
        (out/'data/provenance.json').write_text(json.dumps(metadata,indent=2)+'\n')
    else:
        (out/f'data/provenance_{args.start:03d}_{args.stop:03d}.json').write_text(json.dumps(metadata,indent=2)+'\n')
print(json.dumps({'phase':'complete','plots':len(events),'plot_bytes':sum((out/e['plot']).stat().st_size for e in events)}),flush=True)
