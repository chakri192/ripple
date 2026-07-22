"""Ripple web dashboard.

A single-file FastAPI app: paste a broken URN, see the ranked impact and a
lineage graph with the blast radius highlighted. The /api/triage endpoint is
READ-ONLY (no catalog writes) — safe to click around in a demo. Light + dark
themes with a toggle; no external JS/CDN dependencies.

    python -m ripple web            # then open http://localhost:8000
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse

from .config import Config
from .datahub_client import DataHubClient

app = FastAPI(title="Ripple")


@app.get("/api/triage")
def api_triage(urn: str) -> JSONResponse:
    """Read-only blast-radius analysis for a URN."""
    client = DataHubClient(Config.from_env())
    assets = client.downstream_lineage(urn)
    graph = client.blast_graph(urn, downstream=assets)
    owners = sorted({o for a in assets for o in a.owners})
    cf = [a for a in assets if a.is_customer_facing]
    sev = "SEV1" if cf else ("SEV2" if assets else "SEV3")
    return JSONResponse(
        {
            "severity": sev,
            "total": len(assets),
            "customer_facing": len(cf),
            "platforms": len({a.platform for a in assets}),
            "page_owners": sorted({o for a in cf for o in a.owners}),
            "owners": owners,
            "graph": graph,
            "assets": [
                {
                    "name": a.name,
                    "type": a.entity_type,
                    "platform": a.platform,
                    "hops": a.hops,
                    "owners": a.owners,
                    "cf": a.is_customer_facing,
                    "criticality": a.criticality,
                }
                for a in sorted(assets, key=lambda x: x.criticality, reverse=True)
            ],
        }
    )


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return _PAGE


def serve(port: int = 8000) -> None:
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=port)


_PAGE = """
<!doctype html>
<html lang="en" data-theme="light">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Ripple — data incident triage</title>
<style>
  :root{
    --bg:#f7f8fa; --panel:#ffffff; --panel2:#f2f4f7; --line:#e5e7eb;
    --line2:#c2c8d0; --text:#0f172a; --text2:#334155; --dim:#667085;
    --accent:#111827; --accent2:#000000; --on-accent:#ffffff;
    --red:#dc2626; --redbg:rgba(220,38,38,.07); --amber:#b45309;
    --green:#047857; --greenbg:rgba(4,120,87,.10);
    --src-bg:#eceff3; --src-text:#111827;
    --shadow:0 1px 2px rgba(15,23,42,.05), 0 2px 8px rgba(15,23,42,.05);
    --radius:14px; --r-sm:10px;
  }
  html[data-theme="dark"]{
    --bg:#0b0c0e; --panel:#141517; --panel2:#101113; --line:#26282c;
    --line2:#3a3d42; --text:#f3f4f6; --text2:#c7cad1; --dim:#8b8f98;
    --accent:#f3f4f6; --accent2:#ffffff; --on-accent:#0b0c0e;
    --red:#f87171; --redbg:rgba(248,113,113,.14); --amber:#fbbf24;
    --green:#34d399; --greenbg:rgba(52,211,153,.12);
    --src-bg:#1c1f24; --src-text:#e5e7eb;
    --shadow:0 1px 2px rgba(0,0,0,.4), 0 2px 10px rgba(0,0,0,.32);
  }
  *{box-sizing:border-box}
  html,body{margin:0}
  body{background:var(--bg); color:var(--text);
    font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
    font-size:14px; line-height:1.5; -webkit-font-smoothing:antialiased;}
  .mono{font-family:ui-monospace,SFMono-Regular,Menlo,monospace}
  a{color:var(--accent)}

  /* top bar */
  .topbar{position:sticky; top:0; z-index:10; background:var(--panel);
    border-bottom:1px solid var(--line); display:flex; align-items:center;
    gap:12px; padding:12px 22px;}
  .brand{display:flex; align-items:baseline; gap:8px; font-size:15px}
  .brand .logo{color:var(--accent); font-weight:750; letter-spacing:-.01em}
  .brand .muted{color:var(--dim); font-weight:500; font-size:13px}
  .spacer{margin-left:auto}
  .badge{font-size:11px; color:var(--dim); border:1px solid var(--line);
    padding:3px 9px; border-radius:999px}
  .icon-btn{background:var(--panel2); border:1px solid var(--line); color:var(--text);
    width:34px; height:34px; border-radius:9px; cursor:pointer; font-size:15px;
    display:inline-flex; align-items:center; justify-content:center}
  .icon-btn:hover{border-color:var(--line2)}

  .container{max-width:1140px; margin:0 auto; padding:26px 22px 60px}

  /* hero / search */
  .hero h1{font-size:24px; margin:0 0 4px; letter-spacing:-.02em}
  .hero p{margin:0 0 16px; color:var(--dim)}
  .searchbar{display:flex; gap:10px}
  .searchbar input{flex:1; background:var(--panel); border:1px solid var(--line);
    color:var(--text); padding:12px 14px; border-radius:var(--r-sm); font-size:13px;
    box-shadow:var(--shadow); font-family:ui-monospace,Menlo,monospace}
  .searchbar input:focus{outline:none; border-color:var(--accent)}
  .btn{border:0; border-radius:var(--r-sm); font-weight:600; cursor:pointer; font-size:14px}
  .btn-primary{background:var(--accent); color:var(--on-accent); padding:12px 22px}
  .btn-primary:hover{background:var(--accent2)}

  .placeholder{margin-top:40px; text-align:center; color:var(--dim);
    border:1px dashed var(--line); border-radius:var(--radius); padding:52px}

  /* summary */
  .results{margin-top:22px; display:flex; flex-direction:column; gap:18px}
  .summary{display:grid; grid-template-columns:auto repeat(4,1fr); gap:12px; align-items:stretch}
  .sevcard{display:flex; flex-direction:column; justify-content:center; align-items:center;
    min-width:96px; border-radius:var(--radius); padding:12px 18px; font-weight:800;
    font-size:20px; letter-spacing:.02em}
  .sev1{background:var(--redbg); color:var(--red); border:1px solid var(--red)}
  .sev2{background:rgba(180,83,9,.10); color:var(--amber); border:1px solid var(--amber)}
  .sev3{background:var(--greenbg); color:var(--green); border:1px solid var(--green)}
  .stat{background:var(--panel); border:1px solid var(--line); border-radius:var(--radius);
    padding:14px 16px; box-shadow:var(--shadow)}
  .stat.hot{border-color:var(--red)}
  .stat .n{font-size:26px; font-weight:700; line-height:1}
  .stat.hot .n{color:var(--red)}
  .stat .l{font-size:11px; color:var(--dim); text-transform:uppercase; letter-spacing:.05em; margin-top:7px}

  /* panels */
  .panel{background:var(--panel); border:1px solid var(--line); border-radius:var(--radius);
    box-shadow:var(--shadow); overflow:hidden}
  .panel-head{display:flex; align-items:center; gap:12px; padding:14px 18px;
    border-bottom:1px solid var(--line)}
  .panel-head h2{font-size:14px; margin:0; font-weight:650}
  .legend{margin-left:auto; display:flex; gap:14px; font-size:12px; color:var(--dim)}
  .legend i{display:inline-block; width:11px; height:11px; border-radius:3px;
    margin-right:5px; vertical-align:-1px; border:1px solid var(--line2)}
  .sw-src{background:var(--src-bg); border-color:var(--accent)}
  .sw-tbl{background:var(--panel)}
  .sw-cf{background:var(--redbg); border-color:var(--red)}

  .graph{padding:14px; overflow:auto; max-height:560px}
  .graph svg text{user-select:none}
  .graph g.node:hover rect{stroke-width:2.5}

  .grid-2{display:grid; grid-template-columns:1.6fr 1fr; gap:18px}
  @media (max-width:880px){ .grid-2{grid-template-columns:1fr}
    .summary{grid-template-columns:1fr 1fr} }

  table{width:100%; border-collapse:collapse; font-size:13px}
  th,td{text-align:left; padding:11px 18px; border-bottom:1px solid var(--line)}
  th{color:var(--dim); font-weight:600; font-size:11px; text-transform:uppercase; letter-spacing:.04em}
  tbody tr:last-child td{border-bottom:0}
  tbody tr:hover{background:var(--panel2)}
  .cf-dot{color:var(--red); font-weight:800}

  .actions{list-style:none; margin:0; padding:8px}
  .actions li{display:flex; gap:10px; align-items:flex-start; padding:10px 12px;
    border-radius:var(--r-sm); font-size:13px}
  .actions li:hover{background:var(--panel2)}
  .actions .k{color:var(--accent); font-weight:700}
  .foot{margin-top:26px; text-align:center; color:var(--dim); font-size:12px}
</style>
</head>
<body>
  <div class="topbar">
    <span class="brand"><span class="logo">Ripple</span> <span class="muted">for DataHub</span></span>
    <span class="spacer"></span>
    <span class="badge">read-only</span>
    <button id="themeBtn" class="icon-btn" title="Toggle light / dark" aria-label="Toggle theme"></button>
  </div>

  <div class="container">
    <section class="hero">
      <h1>Data incident triage</h1>
      <p>Paste a broken asset's URN to trace its blast radius across DataHub lineage.</p>
      <div class="searchbar">
        <input id="urn" spellcheck="false"
          value="urn:li:dataset:(urn:li:dataPlatform:snowflake,prod.raw.orders_raw,PROD)"/>
        <button class="btn btn-primary" id="go">Triage</button>
      </div>
    </section>

    <section id="empty" class="placeholder">Enter a URN and hit <b>Triage</b> to trace the blast radius.</section>

    <section id="results" class="results" hidden>
      <div class="summary">
        <div class="sevcard sev1" id="pill">SEV1</div>
        <div class="stat"><div class="n" id="s-total">–</div><div class="l">assets affected</div></div>
        <div class="stat hot"><div class="n" id="s-cf">–</div><div class="l">customer-facing</div></div>
        <div class="stat"><div class="n" id="s-own">–</div><div class="l">owners to page</div></div>
        <div class="stat"><div class="n" id="s-plat">–</div><div class="l">platforms</div></div>
      </div>

      <div class="panel">
        <div class="panel-head">
          <h2>Blast radius</h2>
          <div class="legend">
            <span><i class="sw-src"></i>source</span>
            <span><i class="sw-tbl"></i>table</span>
            <span><i class="sw-cf"></i>customer-facing</span>
          </div>
        </div>
        <div id="graph" class="graph"></div>
      </div>

      <div class="grid-2">
        <div class="panel">
          <div class="panel-head"><h2>Ranked impact</h2></div>
          <table id="tbl"><thead><tr>
            <th>Asset</th><th>Type</th><th>Platform</th><th>Hops</th><th>Owners</th><th>CF</th>
          </tr></thead><tbody></tbody></table>
        </div>
        <div class="panel">
          <div class="panel-head"><h2>Recommended actions</h2></div>
          <ul class="actions" id="actions"></ul>
        </div>
      </div>
    </section>

    <div class="foot">Read-only preview · Ripple for the DataHub Agent Hackathon</div>
  </div>

<script>
  // ---- theme ----
  const root = document.documentElement, tbtn = document.getElementById('themeBtn');
  const SUN = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="4.2"/><path d="M12 2.5v2.4M12 19.1v2.4M4.6 4.6l1.7 1.7M17.7 17.7l1.7 1.7M2.5 12h2.4M19.1 12h2.4M4.6 19.4l1.7-1.7M17.7 6.3l1.7-1.7"/></svg>';
  const MOON = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.8A9 9 0 1 1 11.2 3 7 7 0 0 0 21 12.8z"/></svg>';
  function setTheme(t){ root.setAttribute('data-theme', t);
    tbtn.innerHTML = t === 'dark' ? SUN : MOON;
    try{ localStorage.setItem('ripple-theme', t); }catch(e){} }
  (function(){ let t; try{ t = localStorage.getItem('ripple-theme'); }catch(e){}
    if(!t) t = matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
    setTheme(t); })();
  tbtn.onclick = () => setTheme(root.getAttribute('data-theme') === 'dark' ? 'light' : 'dark');

  const esc = s => String(s).replace(/[&<>]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
  const clip = (s,n) => s.length > n ? s.slice(0,n-1) + '…' : s;

  async function triage(){
    const urn = document.getElementById('urn').value.trim();
    if(!urn) return;
    const go = document.getElementById('go'); go.textContent = 'Tracing…'; go.disabled = true;
    let r;
    try { r = await (await fetch('/api/triage?urn=' + encodeURIComponent(urn))).json(); }
    catch(e){ alert('Error: ' + e); go.textContent='Triage'; go.disabled=false; return; }
    go.textContent = 'Triage'; go.disabled = false;

    document.getElementById('empty').hidden = true;
    document.getElementById('results').hidden = false;

    const pill = document.getElementById('pill');
    pill.textContent = r.severity;
    pill.className = 'sevcard ' + (r.severity==='SEV1'?'sev1':r.severity==='SEV2'?'sev2':'sev3');
    document.getElementById('s-total').textContent = r.total;
    document.getElementById('s-cf').textContent = r.customer_facing;
    document.getElementById('s-own').textContent = r.owners.length;
    document.getElementById('s-plat').textContent = r.platforms;

    const tb = document.querySelector('#tbl tbody'); tb.innerHTML = '';
    for(const a of r.assets){
      tb.insertAdjacentHTML('beforeend',
        '<tr><td>'+esc(a.name)+'</td><td>'+esc(a.type.toLowerCase())+'</td><td>'+
        esc(a.platform)+'</td><td>'+a.hops+'</td><td>'+esc(a.owners.join(', ')||'—')+
        '</td><td>'+(a.cf?'<span class="cf-dot">●</span>':'')+'</td></tr>');
    }

    const acts = [];
    if(r.page_owners.length) acts.push(['page', esc(r.page_owners.join(', '))+' — they own the customer-facing surfaces']);
    else acts.push(['assign', 'no owners on the customer-facing surfaces']);
    acts.push(['freeze', 'downstream refreshes until the source is validated']);
    acts.push(['log', 'run <span class="mono">ripple triage</span> with write-back to record the incident']);
    document.getElementById('actions').innerHTML =
      acts.map(a => '<li><span class="k">'+a[0]+'</span><span>'+a[1]+'</span></li>').join('');

    renderGraph(r.graph);
  }

  // ---- custom SVG lineage renderer (native resolution, scrollable) ----
  function renderGraph(g){
    const gEl = document.getElementById('graph');
    if(!g.nodes || !g.nodes.length){
      gEl.innerHTML = '<div style="color:var(--dim);padding:48px;text-align:center">No downstream lineage — this asset is a leaf.</div>';
      return;
    }
    const NW=176, NH=56, COLW=248, VGAP=30, PADX=28, PADY=30;
    const byLevel = {}; let maxLevel = 0;
    g.nodes.forEach(n => { (byLevel[n.level]=byLevel[n.level]||[]).push(n);
      if(n.level>maxLevel) maxLevel=n.level; });
    const maxRows = Math.max(1, ...Object.values(byLevel).map(a=>a.length));
    const H = PADY*2 + maxRows*NH + (maxRows-1)*VGAP;
    const W = PADX*2 + (maxLevel+1)*NW + maxLevel*(COLW-NW);
    const pos = {};
    Object.keys(byLevel).forEach(lv => {
      const col = byLevel[lv], colH = col.length*NH + (col.length-1)*VGAP, y0 = (H-colH)/2;
      col.forEach((n,i) => { pos[n.id] = { x:PADX+lv*COLW, y:y0+i*(NH+VGAP), n }; });
    });

    const edges = g.edges.map(e => {
      const a = pos[e.from], b = pos[e.to]; if(!a||!b) return '';
      if(a.n.level === b.n.level){
        const x1=a.x+NW/2, y1=a.y+NH, x2=b.x+NW/2, y2=b.y, my=(y1+y2)/2;
        return `<path d="M${x1},${y1} C${x1},${my} ${x2},${my} ${x2},${y2}" fill="none" stroke="var(--line2)" stroke-width="1.5" marker-end="url(#a)"/>`;
      }
      const x1=a.x+NW, y1=a.y+NH/2, x2=b.x, y2=b.y+NH/2, mx=(x1+x2)/2;
      return `<path d="M${x1},${y1} C${mx},${y1} ${mx},${y2} ${x2},${y2}" fill="none" stroke="var(--line2)" stroke-width="1.5" marker-end="url(#a)"/>`;
    }).join('');

    const cards = g.nodes.map(n => {
      const p = pos[n.id], isSrc = n.kind==='SOURCE',
        isDash = ['DASHBOARD','CHART'].includes(n.kind);
      const fill = isSrc?'var(--src-bg)':(n.cf?'var(--redbg)':'var(--panel2)');
      const stroke = isSrc?'var(--accent)':(n.cf?'var(--red)':'var(--line2)');
      const tcol = isSrc?'var(--src-text)':(n.cf?'var(--red)':'var(--text)');
      const sub = (isDash?'dashboard':isSrc?'source':'table')+' · '+esc(n.platform);
      return `<g class="node"><title>${esc(n.label)} — ${sub}</title>
        <rect x="${p.x}" y="${p.y}" width="${NW}" height="${NH}" rx="11" fill="${fill}" stroke="${stroke}" stroke-width="1.5"/>
        <text x="${p.x+16}" y="${p.y+24}" font-size="13.5" font-weight="600" fill="${tcol}">${esc(clip(n.label,20))}</text>
        <text x="${p.x+16}" y="${p.y+41}" font-size="11" fill="var(--dim)" font-family="ui-monospace,Menlo,monospace">${sub}</text>
      </g>`;
    }).join('');

    gEl.innerHTML =
      `<svg width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" style="display:block;margin:0 auto;font-family:-apple-system,Segoe UI,sans-serif">
        <defs><marker id="a" markerWidth="7" markerHeight="7" refX="6" refY="3.5" orient="auto"><path d="M0,0 L6,3.5 L0,7 Z" fill="var(--line2)"/></marker></defs>
        ${edges}${cards}
      </svg>`;
  }

  document.getElementById('go').onclick = triage;
  document.getElementById('urn').addEventListener('keydown', e => { if(e.key==='Enter') triage(); });
  triage();
</script>
</body>
</html>
"""
