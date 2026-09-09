
const CONFIG = window.TDN_CONFIG || {};
const API_URL = CONFIG.APPS_SCRIPT_URL || "";
const API_CONFIGURED = API_URL && !API_URL.includes("PASTE_YOUR_");

const mb=document.querySelector('.menu-button'), mn=document.querySelector('.mobile-nav');
if(mb&&mn){mb.addEventListener('click',()=>{const open=mn.classList.toggle('open');mb.setAttribute('aria-expanded',String(open));mb.textContent=open?'×':'☰';});}

function esc(value){
  return String(value ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[ch]));
}

async function fileToBase64(file){
  return new Promise((resolve,reject)=>{
    const reader=new FileReader();
    reader.onload=()=>resolve(String(reader.result).split(',')[1] || '');
    reader.onerror=reject;
    reader.readAsDataURL(file);
  });
}

document.querySelectorAll('.demo-form').forEach(form=>{
  form.addEventListener('submit', async e=>{
    e.preventDefault();
    const status=form.querySelector('.form-status');
    const button=form.querySelector('button[type="submit"]');
    const original=button ? button.textContent : '';
    const hp=form.querySelector('[name="website"]');

    if(hp && hp.value) return; // honeypot

    if(!API_CONFIGURED){
      if(status){
        status.textContent='This form is ready, but the Google Apps Script URL still needs to be added in assets/config.js before launch.';
        status.className='form-status error';
      }
      return;
    }

    try{
      if(button){button.disabled=true;button.textContent='Sending…';}
      if(status){status.textContent='';status.className='form-status';}

      const data=new FormData(form);
      const payload=new URLSearchParams();
      payload.set('action','form');
      payload.set('formType',form.dataset.formType || 'website_enquiry');
      payload.set('pageUrl',window.location.href);
      payload.set('submittedAt',new Date().toISOString());

      for(const [key,value] of data.entries()){
        if(value instanceof File){
          if(value && value.size){
            if(value.size > 5 * 1024 * 1024){
              throw new Error('Please upload a CV smaller than 5 MB.');
            }
            payload.set('cvName',value.name);
            payload.set('cvType',value.type || 'application/octet-stream');
            payload.set('cvBase64',await fileToBase64(value));
          }
        } else {
          payload.set(key,value);
        }
      }

      const response=await fetch(API_URL,{
        method:'POST',
        headers:{'Content-Type':'application/x-www-form-urlencoded;charset=UTF-8'},
        body:payload.toString(),
        redirect:'follow'
      });

      const result=await response.json();
      if(!result.ok) throw new Error(result.error || 'Your enquiry could not be sent.');

      form.reset();
      if(status){
        status.textContent='Thanks — your enquiry has been sent.';
        status.className='form-status success';
      }
      if(button) button.textContent='Sent ✓';

      setTimeout(()=>{
        if(button){button.disabled=false;button.textContent=original;}
      },3500);

    } catch(err){
      if(status){
        status.textContent=err.message || 'Something went wrong. Please try again.';
        status.className='form-status error';
      }
      if(button){button.disabled=false;button.textContent=original;}
    }
  });
});

async function fetchJobs(){
  if(!API_CONFIGURED) throw new Error('Jobs integration is not configured yet.');
  const response=await fetch(API_URL + '?action=jobs&_=' + Date.now(), {redirect:'follow'});
  const result=await response.json();
  if(!result.ok) throw new Error(result.error || 'Could not load opportunities.');
  return Array.isArray(result.jobs) ? result.jobs : [];
}

function jobCard(job){
  const id=encodeURIComponent(job.jobId || '');
  const title=esc(job.positionTitle || 'Medical opportunity');
  const specialty=esc(job.specialty || '');
  const location=esc(job.location || '');
  const state=esc(job.state || '');
  const type=esc(job.employmentType || '');
  const sector=esc(job.sector || '');
  const summary=esc(job.shortSummary || '');
  const search=esc(`${job.positionTitle||''} ${job.specialty||''} ${job.location||''}`.toLowerCase());

  return `<article class="job-card"
    data-search="${search}"
    data-specialty="${specialty}"
    data-state="${state}"
    data-type="${type}"
    data-sector="${sector}">
    <div class="pills">${type?`<span class="pill">${type}</span>`:''}${sector?`<span class="pill">${sector}</span>`:''}</div>
    <h3>${title}</h3>
    <p>${summary}</p>
    <div class="job-meta">${specialty}${specialty&&location?' · ':''}${location}</div>
    <a class="text-link" href="opportunity.html?id=${id}">View opportunity →</a>
  </article>`;
}

function fillSelect(id, values, firstLabel){
  const el=document.getElementById(id);
  if(!el) return;
  const unique=[...new Set(values.filter(Boolean))].sort((a,b)=>a.localeCompare(b));
  el.innerHTML=`<option value="">${firstLabel}</option>`+unique.map(v=>`<option>${esc(v)}</option>`).join('');
}

function activateJobFilters(cards){
  const controls=['search','specialty','state','type','sector'].map(id=>document.getElementById(id)).filter(Boolean);
  if(!controls.length) return;
  function filter(){
    const q=(document.getElementById('search')?.value||'').toLowerCase();
    const sp=document.getElementById('specialty')?.value||'';
    const st=document.getElementById('state')?.value||'';
    const ty=document.getElementById('type')?.value||'';
    const se=document.getElementById('sector')?.value||'';
    let shown=0;
    cards.forEach(c=>{
      const ok=(!q||c.dataset.search.includes(q))&&(!sp||c.dataset.specialty===sp)&&(!st||c.dataset.state===st)&&(!ty||c.dataset.type===ty)&&(!se||c.dataset.sector===se);
      c.style.display=ok?'block':'none';
      if(ok) shown++;
    });
    const status=document.getElementById('jobsStatus');
    if(status) status.textContent=shown ? `${shown} current opportunit${shown===1?'y':'ies'}` : 'No current opportunities match those filters.';
  }
  controls.forEach(c=>c.addEventListener('input',filter));
  filter();
}

async function loadJobsPage(){
  const grid=document.getElementById('jobsGrid');
  if(!grid) return;
  const status=document.getElementById('jobsStatus');
  try{
    const jobs=await fetchJobs();
    if(!jobs.length){
      grid.innerHTML='';
      if(status) status.innerHTML='There are no public opportunities listed right now. <a class="text-link" href="join.html">Join the Network →</a>';
      return;
    }
    grid.innerHTML=jobs.map(jobCard).join('');
    fillSelect('specialty',jobs.map(j=>j.specialty),'All specialties');
    fillSelect('state',jobs.map(j=>j.state),'All states');
    fillSelect('type',jobs.map(j=>j.employmentType),'Permanent / Locum');
    fillSelect('sector',jobs.map(j=>j.sector),'Private / Public');
    activateJobFilters([...grid.querySelectorAll('.job-card')]);
  }catch(err){
    grid.innerHTML='';
    if(status){
      status.innerHTML=API_CONFIGURED
        ? `Current opportunities could not be loaded. <a class="text-link" href="join.html">Join the Network →</a>`
        : `Jobs are ready to connect to the Google Sheet. Add the Apps Script URL in <strong>assets/config.js</strong> before launch.`;
    }
  }
}

async function loadHomeJobs(){
  const grid=document.getElementById('homeJobsGrid');
  if(!grid) return;
  const status=document.getElementById('homeJobsStatus');
  try{
    const jobs=(await fetchJobs()).slice(0,3);
    grid.innerHTML=jobs.map(jobCard).join('');
    if(status) status.style.display='none';
    if(!jobs.length && status){
      status.style.display='block';
      status.innerHTML='No public opportunities are listed right now. <a class="text-link" href="join.html">Join the Network →</a>';
    }
  }catch(err){
    grid.innerHTML='';
    if(status){
      status.innerHTML=API_CONFIGURED
        ? 'Current opportunities are temporarily unavailable.'
        : 'Live opportunities will appear here once the Google Sheet connection is configured.';
    }
  }
}

async function loadJobDetail(){
  const title=document.getElementById('jobTitle');
  if(!title) return;
  const id=new URLSearchParams(location.search).get('id');
  if(!id){
    title.textContent='Opportunity not found';
    return;
  }
  try{
    if(!API_CONFIGURED) throw new Error('Integration not configured');
    const response=await fetch(API_URL + '?action=job&id=' + encodeURIComponent(id) + '&_=' + Date.now(),{redirect:'follow'});
    const result=await response.json();
    if(!result.ok || !result.job) throw new Error('Opportunity not found');
    const j=result.job;

    document.title=`${j.positionTitle || 'Opportunity'} | The Doctor Network`;
    title.textContent=j.positionTitle || 'Medical opportunity';
    document.getElementById('jobSummary').textContent=j.shortSummary || '';
    document.getElementById('jobPills').innerHTML=[j.employmentType,j.sector,j.location].filter(Boolean).map(x=>`<span class="pill">${esc(x)}</span>`).join('');
    document.getElementById('enquiryJobId').value=j.jobId || '';
    document.getElementById('enquiryJobTitle').value=j.positionTitle || '';

    const detail=document.getElementById('jobDetail');
    const parts=[];
    if(j.overview) parts.push(`<h2>Overview</h2><p>${esc(j.overview).replace(/\n/g,'<br>')}</p>`);
    if(j.roleDetails) parts.push(`<h3>Role details</h3><p>${esc(j.roleDetails).replace(/\n/g,'<br>')}</p>`);
    if(j.whyConsiderIt) parts.push(`<h3>Why consider the opportunity</h3><p>${esc(j.whyConsiderIt).replace(/\n/g,'<br>')}</p>`);
    if(j.locationInformation) parts.push(`<h3>Location</h3><p>${esc(j.locationInformation).replace(/\n/g,'<br>')}</p>`);
    if(j.salaryRate) parts.push(`<div class="job-detail-meta"><span class="pill">${esc(j.salaryRate)}</span></div>`);
    detail.innerHTML=parts.join('') || '<p>Further details are available in a confidential conversation.</p>';

    const schema={
      "@context":"https://schema.org",
      "@type":"JobPosting",
      "title":j.positionTitle || '',
      "description":j.overview || j.shortSummary || '',
      "employmentType":j.employmentType || '',
      "identifier":{"@type":"PropertyValue","name":"The Doctor Network","value":j.jobId || ''},
      "jobLocation":{"@type":"Place","address":{"@type":"PostalAddress","addressRegion":j.state || '',"addressCountry":"AU"}}
    };
    const script=document.createElement('script');
    script.type='application/ld+json';
    script.textContent=JSON.stringify(schema);
    document.head.appendChild(script);
  }catch(err){
    title.textContent='Opportunity not found';
    document.getElementById('jobSummary').textContent='This role may have closed or is no longer published. You can still join the network for future opportunities.';
    document.getElementById('jobDetail').innerHTML='<a class="button coral" href="join.html">Join the Network</a>';
  }
}

loadJobsPage();
loadHomeJobs();
loadJobDetail();

// Premium smiley cursor
const brandCursor = document.querySelector('.brand-cursor');
if (brandCursor && window.matchMedia('(pointer:fine)').matches) {
  let x = window.innerWidth / 2, y = window.innerHeight / 2;
  let cx = x, cy = y;
  const follow = () => {
    cx += (x - cx) * 0.28;
    cy += (y - cy) * 0.28;
    brandCursor.style.left = cx + 'px';
    brandCursor.style.top = cy + 'px';
    requestAnimationFrame(follow);
  };
  window.addEventListener('mousemove', e => { x=e.clientX; y=e.clientY; brandCursor.style.opacity='1'; });
  document.addEventListener('mouseleave',()=>brandCursor.style.opacity='0');
  document.addEventListener('mouseenter',()=>brandCursor.style.opacity='1');
  document.addEventListener('mouseover',e=>{
    if(e.target.closest('a,button,input,select,textarea,.job-card,.journey-card')) brandCursor.classList.add('is-hovering');
  });
  document.addEventListener('mouseout',e=>{
    if(e.target.closest('a,button,input,select,textarea,.job-card,.journey-card')) brandCursor.classList.remove('is-hovering');
  });
  window.addEventListener('mousedown',()=>brandCursor.classList.add('is-clicking'));
  window.addEventListener('mouseup',()=>brandCursor.classList.remove('is-clicking'));
  follow();
}

// Scroll reveal
const reveals=[...document.querySelectorAll('.reveal')];
if('IntersectionObserver' in window){
  const observer=new IntersectionObserver(entries=>{
    entries.forEach(entry=>{
      if(entry.isIntersecting){entry.target.classList.add('in-view');observer.unobserve(entry.target);}
    });
  },{threshold:.12});
  reveals.forEach(el=>observer.observe(el));
}else{
  reveals.forEach(el=>el.classList.add('in-view'));
}
