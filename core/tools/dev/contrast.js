/* 글자 대비 점검(WCAG AA: 보통 4.5, 큰 글자 3) — regress.py 가 page.evaluate 로 실행. 결과 = 기준 미달 글자 목록. 사진·그라데이션 바탕(배경 이미지)은 계산 못 해서 뺌 */
() => {
  function rgb(s){const k=s.match(/color\(srgb ([^)]+)\)/); if(k){const q=k[1].split(/[ \/]+/).filter(Boolean).map(Number); return {r:q[0]*255,g:q[1]*255,b:q[2]*255,a:q.length>3?q[3]:1};}const m=s.match(/rgba?\(([^)]+)\)/); if(!m) return null; const p=m[1].split(/[ ,\/]+/).filter(Boolean).map(Number); return {r:p[0],g:p[1],b:p[2],a:p.length>3?p[3]:1};}
  function lum(c){const f=v=>{v/=255;return v<=0.03928?v/12.92:Math.pow((v+0.055)/1.055,2.4)};return 0.2126*f(c.r)+0.7152*f(c.g)+0.0722*f(c.b);}
  function bg(el){let cs=[];for(let e=el;e;e=e.parentElement){const s=getComputedStyle(e);if(s.backgroundImage&&s.backgroundImage!=='none')return null;const c=rgb(s.backgroundColor);if(c&&c.a>0){cs.push(c);if(c.a>=1)break;}}
    let out={r:255,g:255,b:255};for(let i=cs.length-1;i>=0;i--){const c=cs[i];out={r:c.r*c.a+out.r*(1-c.a),g:c.g*c.a+out.g*(1-c.a),b:c.b*c.a+out.b*(1-c.a)};}return out;}
  const res=[];const seen=new Set();
  const w=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT);let n;
  while((n=w.nextNode())){const t=n.textContent.trim();if(!t)continue;const el=n.parentElement;if(!el||seen.has(el))continue;seen.add(el);
    const r=el.getBoundingClientRect();if(!r.width||!r.height)continue;const s=getComputedStyle(el);if(s.visibility==='hidden'||+s.opacity===0)continue;
    if(el.closest('[hidden],.dm-ad,[aria-hidden="true"],#topGrid,.toast'))continue;
    let op=1;for(let e=el;e;e=e.parentElement)op*=+getComputedStyle(e).opacity;
    const fg=rgb(s.color);const b=bg(el);if(!fg||!b)continue;
    const f={r:fg.r*fg.a*op+b.r*(1-fg.a*op),g:fg.g*fg.a*op+b.g*(1-fg.a*op),b:fg.b*fg.a*op+b.b*(1-fg.a*op)};
    const L1=lum(f),L2=lum(b);const cr=(Math.max(L1,L2)+.05)/(Math.min(L1,L2)+.05);
    const fs=parseFloat(s.fontSize),bold=+s.fontWeight>=700;const need=(fs>=24||(fs>=18.66&&bold))?3:4.5;
    if(cr<need)res.push({cr:+cr.toFixed(2),need,fs,cls:(el.className&&el.className.baseVal===undefined?el.className:el.tagName).toString().slice(0,40),tag:el.tagName,t:t.slice(0,30),color:s.color});}
  return res;
}
