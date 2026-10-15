
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

// "19/10/2026" -> "19 Oct 2026"; other text ("ASAP", "Ongoing", "Feb 2027") is shown as written.
function niceDate(v){
  const s=String(v||'').trim();
  const m=s.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/);
  if(!m) return s;
  const months=['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
  const mo=months[parseInt(m[2],10)-1];
  return mo ? `${parseInt(m[1],10)} ${mo} ${m[3]}` : s;
}

function dateRange(job){
  const start=niceDate(job.startDate), end=niceDate(job.endDate);
  if(start && end) return `${start} – ${end}`;
  if(start) return `From ${start}`;
  if(end) return `Until ${end}`;
  return '';
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
  const dates=esc(dateRange(job));
  const rate=esc(job.salaryRate || '');
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
    <div class="job-meta">${specialty}${specialty&&location?' · ':''}${location}${dates?`<div class="job-dates">${dates}</div>`:''}${rate?`<div class="job-rate">${rate}</div>`:''}</div>
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

function setHeadTag(selector,attrs,key,value){
  let el=document.head.querySelector(selector);
  if(!el){
    el=document.createElement(attrs.rel?'link':'meta');
    Object.entries(attrs).forEach(([k,v])=>el.setAttribute(k,v));
    document.head.appendChild(el);
  }
  el.setAttribute(key,value);
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
    const range=dateRange(j);
    if(j.salaryRate || range) parts.push(`<div class="job-detail-meta">${range?`<span class="pill">${esc(range)}</span> `:''}${j.salaryRate?`<span class="pill">${esc(j.salaryRate)}</span>`:''}</div>`);
    detail.innerHTML=parts.join('') || '<p>Further details are available in a confidential conversation.</p>';

    // SEO: page-specific description, canonical and share tags
    const pageUrl='https://thedoctornetwork.com.au/opportunity.html?id='+encodeURIComponent(j.jobId || id);
    const metaDesc=(j.shortSummary || `${j.positionTitle || 'Medical opportunity'} in ${[j.location,j.state].filter(Boolean).join(', ')}`).slice(0,155);
    setHeadTag('meta[name="description"]',{name:'description'},'content',metaDesc);
    setHeadTag('link[rel="canonical"]',{rel:'canonical'},'href',pageUrl);
    setHeadTag('meta[property="og:url"]',{property:'og:url'},'content',pageUrl);
    setHeadTag('meta[property="og:title"]',{property:'og:title'},'content',document.title);
    setHeadTag('meta[property="og:description"]',{property:'og:description'},'content',metaDesc);

    // Google for Jobs structured data (requires title, description, datePosted, hiringOrganization, jobLocation)
    const htmlBlock=(label,text)=>text?`<p><strong>${esc(label)}</strong></p><p>${esc(text).replace(/\n/g,'<br>')}</p>`:'';
    const fullDescription=[
      j.shortSummary?`<p>${esc(j.shortSummary)}</p>`:'',
      htmlBlock('Overview',j.overview),
      htmlBlock('Role details',j.roleDetails),
      htmlBlock('Why consider the opportunity',j.whyConsiderIt),
      htmlBlock('Location',j.locationInformation),
      htmlBlock('Dates',dateRange(j)),
      htmlBlock('Salary / rate',j.salaryRate)
    ].join('') || esc(j.positionTitle || '');
    const typeText=String(j.employmentType || '').toLowerCase();
    const empType=[];
    if(typeText.includes('perm')) empType.push('FULL_TIME');
    if(typeText.includes('locum') || typeText.includes('temp') || typeText.includes('contract')) empType.push('TEMPORARY','CONTRACTOR');
    if(typeText.includes('part')) empType.push('PART_TIME');
    const isoDate=v=>{
      if(!v) return '';
      const au=String(v).trim().match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/); // DD/MM/YYYY from the sheet
      if(au) return `${au[3]}-${au[2].padStart(2,'0')}-${au[1].padStart(2,'0')}`;
      const d=new Date(v); return isNaN(d) ? '' : d.toISOString().slice(0,10);
    };
    const posted=isoDate(j.dateAdded) || isoDate(j.lastUpdated);
    const orgName=(j.organisationDisplay && j.organisationDisplay!=='Confidential') ? j.organisationDisplay : 'The Doctor Network';

    const schema={
      "@context":"https://schema.org",
      "@type":"JobPosting",
      "title":j.positionTitle || '',
      "description":fullDescription,
      "identifier":{"@type":"PropertyValue","name":"The Doctor Network","value":j.jobId || ''},
      "hiringOrganization":{"@type":"Organization","name":orgName,"sameAs":"https://thedoctornetwork.com.au/","logo":"https://thedoctornetwork.com.au/assets/logo-square.png"},
      "jobLocation":{"@type":"Place","address":{"@type":"PostalAddress","addressLocality":j.location || '',"addressRegion":j.state || '',"addressCountry":"AU"}},
      "directApply":true,
      "url":pageUrl
    };
    if(posted) schema.datePosted=posted;
    if(empType.length) schema.employmentType=[...new Set(empType)];
    if(j.specialty) schema.occupationalCategory=j.specialty;
    const salaryMatch=String(j.salaryRate||'').replace(/,/g,'').match(/\d+(\.\d+)?/);
    const salaryNum=salaryMatch?parseFloat(salaryMatch[0]):0;
    if(salaryNum){
      const s=String(j.salaryRate).toLowerCase();
      const unit=(s.includes('hour')||s.includes('/hr')||/\bph\b/.test(s))?'HOUR':s.includes('day')?'DAY':s.includes('week')?'WEEK':(salaryNum>10000?'YEAR':'');
      if(unit) schema.baseSalary={"@type":"MonetaryAmount","currency":"AUD","value":{"@type":"QuantitativeValue","value":salaryNum,"unitText":unit}};
    }
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
