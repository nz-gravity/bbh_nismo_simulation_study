"""Verify either public Dynesty results archive using standard Python."""
import argparse,csv,hashlib,io,json,math,zipfile
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('archive',help='Path to either compact public results ZIP')
args=parser.parse_args()
with zipfile.ZipFile(args.archive) as z:
    assert z.testzip() is None
    names=z.namelist();assert len(names)==len(set(names))
    assert all(not n.startswith('/') and '..' not in n.split('/') for n in names)
    prefix=names[0].split('/')[0]+'/'
    read=lambda n:z.read(prefix+n)
    sums=dict((name,digest) for digest,name in (x.split('  ',1) for x in read('SHA256SUMS').decode().splitlines()))
    assert set(sums)=={n[len(prefix):] for n in names}-{'SHA256SUMS'}
    for name,digest in sums.items():assert hashlib.sha256(read(name)).hexdigest()==digest,name
    m=json.loads(read('manifest.json'));assert m['event_ids']==list(range(100))
    total=0
    for event in m['events']:
        d=f"events/injection_{event['event_id']:03d}/"
        s=json.loads(read(d+'summary.json'));data=read(d+'posterior.csv')
        p=list(csv.DictReader(io.StringIO(data.decode())))
        assert len(p)==s['posterior_rows']==event['posterior_rows']
        assert hashlib.sha256(data).hexdigest()==s['posterior_sha256']==event['posterior_sha256']
        assert all(math.isfinite(float(v)) for row in p for v in row.values())
        assert all(math.isfinite(s[k]) for k in ['log_evidence','log_evidence_err','log_noise_evidence'])
        assert (s['config']['kwargs']['nlive'] if m['kind']=='cheap' else s['sampler_kwargs']['nlive'])==m['nlive']
        if m['kind']=='reference':
            selection=json.loads(read(d+'selection.json'))
            assert selection['retained_rows']==len(p)<=1000
            assert len(selection['indices'])==len(set(selection['indices']))==len(p)
            assert selection['original_rows']==s['original_posterior_rows']
            assert s['comparison_audit']['passed']
        total+=len(p)
    assert total==m['posterior_rows_total']
    print(json.dumps({'verified':True,'event_count':100,'nlive':m['nlive'],'retained_rows':total,'sha256':hashlib.sha256(open(args.archive,'rb').read()).hexdigest()}))
