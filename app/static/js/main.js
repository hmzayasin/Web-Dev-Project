document.addEventListener('DOMContentLoaded',()=>{document.querySelectorAll('.flash').forEach(el=>setTimeout(()=>{el.style.opacity='0'},4500));});
/* Stop double-submits on slow connections: forms marked data-once lock their buttons after the first submit. */
document.addEventListener('submit',e=>{const f=e.target;if(f.matches&&f.matches('form[data-once]'))setTimeout(()=>f.querySelectorAll('button').forEach(b=>{b.disabled=true}),0);});
window.addEventListener('pageshow',e=>{if(e.persisted)document.querySelectorAll('form[data-once] button').forEach(b=>{b.disabled=false});});
