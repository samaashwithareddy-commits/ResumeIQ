/* ResumeIQ — job description analyzer + match result rendering. */
(function () {
  'use strict';

  const RI = window.RI;
  const form = document.getElementById('analyzeForm');
  if (!form) { return; }

  const results = document.getElementById('matchResults');
  const descEl = document.getElementById('jobDescription');
  const titleEl = document.getElementById('jobTitle');
  const companyEl = document.getElementById('jobCompany');
  const urlEl = document.getElementById('jobUrl');
  const analyzeBtn = document.getElementById('analyzeBtn');
  const fetchBtn = document.getElementById('fetchUrlBtn');
  const loadSampleBtn = document.getElementById('loadSampleBtn');
  const emptyLoadSample = document.getElementById('emptyLoadSample');
  const fetchNote = document.getElementById('fetchNote');
  const jdCount = document.getElementById('jdCount');
  const jdCounter = document.getElementById('jdCounter');

  let initial = null;
  let sample = null;
  try { initial = JSON.parse(document.getElementById('matcherInitial').textContent || 'null'); } catch (error) { initial = null; }
  try { sample = JSON.parse(document.getElementById('sampleJob').textContent || 'null'); } catch (error) { sample = null; }

  let activeJobId = initial && initial.job ? initial.job.id : null;

  const esc = RI.escapeHtml;

  function chipList(items, cls, emptyText) {
    const list = (items || []).filter(Boolean);
    if (!list.length) { return '<span class="empty-mini">' + esc(emptyText || 'None') + '</span>'; }
    return '<div class="chips-row">' + list.map(function (item) {
      return '<span class="chip ' + cls + '">' + esc(item) + '</span>';
    }).join('') + '</div>';
  }

  function statusPill(status) {
    const labels = {
      met: 'Met', partial: 'Partial', not_met: 'Not met', not_specified: 'Not specified'
    };
    const label = labels[status] || 'Unknown';
    return '<span class="status-pill status-' + esc(status || 'not_specified') + '">' + esc(label) + '</span>';
  }

  function updateCounter() {
    const length = descEl.value.trim().length;
    jdCount.textContent = length + ' characters';
    jdCounter.classList.toggle('is-short', length < 40);
  }

  function setFetchNote(message, kind) {
    if (!message) {
      fetchNote.textContent = '';
      fetchNote.style.color = '';
      return;
    }
    fetchNote.textContent = message;
    fetchNote.style.color = kind === 'error' ? 'var(--bad)' : 'var(--good)';
  }

  function showLoading() {
    results.innerHTML = '<div class="card"><div class="loading-block">' +
      '<div class="spinner"></div>' +
      '<strong>Extracting skills and scoring your profile…</strong>' +
      '<span class="muted-sm">Comparing required, preferred and bonus requirements against your saved profile.</span>' +
      '</div></div>';
  }

  function showError(message) {
    results.innerHTML = '<div class="card"><div class="notice notice-warn" style="align-items:flex-start;">' +
      '<div><strong>Analysis failed.</strong><br>' + esc(message) + '</div></div>' +
      '<p class="analysis-note">Your job text stays in the form so you can fix the input and try again.</p></div>';
  }

  /* ------------------------------------------------------------------ */
  /* Rendering                                                           */
  /* ------------------------------------------------------------------ */
  function renderCategories(match) {
    const categories = match.categories || [];
    return '<div class="category-list">' + categories.map(function (category) {
      const score = category.status === 'scored' ? Math.round((category.score || 0) * 100) : 0;
      const points = category.status === 'scored'
        ? '<strong>' + (category.points || 0).toFixed(1) + '</strong> / ' + (category.effective_weight || 0).toFixed(1) + ' pts'
        : 'Not applicable';
      return '<div class="category-row ' + (category.status === 'scored' ? '' : 'is-na') + '">' +
        '<div class="category-row-top"><span class="category-name">' + esc(category.label) + '</span>' +
        '<span class="category-points">' + points + '</span></div>' +
        '<div class="progress"><span style="width:' + score + '%"></span></div>' +
        '<p class="category-note">' + esc(category.note) + '</p>' +
        '</div>';
    }).join('') + '</div>';
  }

  function renderExtraction(analysis) {
    const groups = [];
    function group(title, items, cls) {
      if (!items || !items.length) { return; }
      groups.push('<div class="req-group"><h4>' + esc(title) + ' <small>' + items.length + '</small></h4>' +
        chipList(items, cls) + '</div>');
    }
    group('Required technical skills', analysis.required_skills, 'chip-indigo');
    group('Preferred / bonus skills', analysis.preferred_skills, 'chip-soft');
    group('Programming languages', analysis.languages, 'chip-ghost');
    group('Frameworks, tools & platforms', analysis.frameworks_tools, 'chip-ghost');
    group('Soft skills mentioned', analysis.soft_skills, 'chip-ghost');

    const facts = [];
    if (analysis.required_years !== null && analysis.required_years !== undefined) {
      facts.push('<span class="chip chip-ghost">Experience: ' + esc(String(analysis.required_years)) + '+ years</span>');
    }
    if (analysis.education_requirements && analysis.education_requirements.length) {
      facts.push('<span class="chip chip-ghost">Education: ' + esc(analysis.education_requirements[0].slice(0, 70)) + '</span>');
    }

    return '<div class="req-block">' + groups.join('') +
      (facts.length ? '<div class="facts-strip">' + facts.join('') + '</div>' : '') +
      (analysis.responsibilities && analysis.responsibilities.length
        ? '<div class="req-group"><h4>Responsibilities <small>' + analysis.responsibilities.length + '</small></h4>' +
          '<ul class="detail-list">' + analysis.responsibilities.map(function (item) { return '<li>' + esc(item) + '</li>'; }).join('') + '</ul></div>'
        : '') +
      (analysis.keywords && analysis.keywords.length
        ? '<div class="req-group"><h4>Role keywords <small>' + analysis.keywords.length + '</small></h4>' + chipList(analysis.keywords, 'chip-ghost') + '</div>'
        : '') +
      '<p class="analysis-note">Extracted with a fixed skill taxonomy and section detection. ' +
      (analysis.notes && analysis.notes.length ? esc(analysis.notes.join(' ')) : 'No extraction warnings.') + '</p>' +
      '</div>';
  }

  function renderScore(payload) {
    const match = payload.match;
    const analysis = payload.analysis;
    const job = payload.job || {};
    const warnings = payload.warnings || [];
    const score = Math.round(match.score);
    const summary = payload.candidate_name
      ? 'Scored against ' + payload.candidate_name + '’s saved profile.'
      : 'Scored against your saved master profile.';

    let html = '';
    if (warnings.length) {
      html += '<div class="warning-list">' + warnings.map(function (warning) {
        return '<li>' + esc(warning) + '</li>';
      }).join('') + '</div>';
    }

    html += '<section class="score-hero">' +
      '<div class="donut" style="--value:' + score + '"><span>' + score + '<small>%</small></span></div>' +
      '<div class="score-hero-copy">' +
        '<span class="eyebrow">Overall match</span>' +
        '<h2>' + esc(match.label) + '</h2>' +
        '<p>' + esc(summary) + '</p>' +
        '<div class="score-hero-role">' +
          (job.title ? '<span class="chip chip-ghost">' + esc(job.title) + '</span>' : '') +
          (job.company ? '<span class="chip chip-ghost">' + esc(job.company) + '</span>' : '') +
          '<span class="chip chip-ghost">' + (analysis.word_count || 0) + ' words analysed</span>' +
        '</div>' +
      '</div>' +
      '<div class="score-actions">' +
        '<button class="btn btn-primary" type="button" data-match-action="build">Create tailored resume</button>' +
        '<a class="btn btn-ghost" href="/builder">Open builder</a>' +
      '</div>' +
    '</section>';

    html += '<section class="card">' +
      '<div class="section-title-row"><div><h3>Why this score</h3>' +
      '<p>Required 50%, preferred 20%, projects &amp; experience 20%, education/other 10%. Missing categories are redistributed.</p></div>' +
      '<span class="chip chip-ghost">' + (match.renormalised ? 'Weights renormalised' : 'All categories applied') + '</span></div>' +
      renderCategories(match) +
      '<div class="facts-strip" style="margin-top:12px;">' +
        Object.keys(match.effective_weights || {}).map(function (key) {
          return '<span class="chip chip-ghost">' + esc(RI.SECTION_LABELS[key] || key) + ' · ' + match.effective_weights[key] + '%</span>';
        }).join('') +
      '</div>' +
      '<p class="disclaimer">' + esc(match.disclaimer) + '</p>' +
    '</section>';

    html += '<section class="card">' +
      '<div class="section-title-row"><div><h3>Skill alignment</h3>' +
      '<p>Only evidence that exists on your profile counts. Gaps are learning targets, not things to fake.</p></div></div>' +
      '<div class="skill-panels">' +
        '<div class="skill-panel"><h4>Matched <span>' + (match.matched_skills || []).length + '</span></h4>' +
          chipList(match.matched_skills, 'chip-good', 'Nothing matched yet') + '</div>' +
        '<div class="skill-panel"><h4>Missing <span>' + (match.missing_skills || []).length + '</span></h4>' +
          chipList(match.missing_skills, 'chip-bad', 'No required gaps') + '</div>' +
        '<div class="skill-panel"><h4>Partially matched <span>' + (match.partial_skills || []).length + '</span></h4>' +
          ((match.partial_skills || []).length
            ? '<ul class="partial-list">' + match.partial_skills.map(function (item) {
                return '<li><b>' + esc(item.skill) + '</b> ≈ ' + esc(item.matched_with) + '</li>';
              }).join('') + '</ul>'
            : '<span class="empty-mini">No partial matches</span>') +
        '</div>' +
      '</div>' +
      ((match.relevant_projects || []).length
        ? '<div style="margin-top:16px;"><span class="mini-label">Relevant projects</span><ul class="detail-list">' +
          match.relevant_projects.map(function (project) {
            return '<li><strong>' + esc(project.name) + '</strong> — ' + esc((project.matched || []).join(', ')) + '</li>';
          }).join('') + '</ul></div>'
        : '') +
    '</section>';

    html += '<section class="card">' +
      '<div class="section-title-row"><div><h3>Education &amp; experience</h3>' +
      '<p>Separate from keyword coverage — these are qualification checks.</p></div></div>' +
      '<div class="alignment-grid">' +
        '<div class="alignment-card"><div class="alignment-head"><h4>Experience alignment</h4>' +
          statusPill(match.experience_alignment.status) + '</div>' +
          '<p>' + esc(match.experience_alignment.note) + '</p></div>' +
        '<div class="alignment-card"><div class="alignment-head"><h4>Education alignment</h4>' +
          statusPill(match.education_alignment.status) + '</div>' +
          '<p>' + esc(match.education_alignment.note) + '</p></div>' +
      '</div>' +
    '</section>';

    html += '<section class="card">' +
      '<div class="section-title-row"><div><h3>Keywords</h3>' +
      '<p>Keyword similarity is informational — it is not part of the score.</p></div>' +
      '<span class="chip chip-ghost">' + (match.keywords.similarity || 0) + '% keyword overlap</span></div>' +
      '<span class="mini-label">Matched keywords</span>' +
      (match.keywords.matched.length ? chipList(match.keywords.matched, 'chip-good') : '<p class="empty-mini">None yet</p>') +
      '<span class="mini-label" style="margin-top:12px;">Important missing keywords</span>' +
      (match.keywords.missing.length ? chipList(match.keywords.missing, 'chip-bad') : '<p class="empty-mini">All detected keywords appear in your profile</p>') +
      '<p class="analysis-note">Add a keyword only if it is genuinely true for you and supported by a project or role.</p>' +
    '</section>';

    html += '<section class="card">' +
      '<div class="section-title-row"><div><h3>Score explanation</h3><p>Every calculation, in plain language.</p></div></div>' +
      '<ol class="explain-list">' + (match.explanation || []).map(function (line, index) {
        return '<li><span>' + (index + 1) + '</span><p>' + esc(line) + '</p></li>';
      }).join('') + '</ol>' +
    '</section>';

    html += '<section class="card">' +
      '<div class="section-title-row"><div><h3>What the job actually asks for</h3>' +
      '<p>Extracted verbatim-ish from your pasted description.</p></div></div>' +
      renderExtraction(analysis) +
    '</section>';

    return html;
  }

  function renderInitial() {
    if (!initial || !initial.match) { return; }
    if (initial.job) {
      titleEl.value = initial.job.title || '';
      companyEl.value = initial.job.company || '';
      urlEl.value = initial.job.url || '';
      descEl.value = initial.job.description || '';
      updateCounter();
    }
    results.innerHTML = renderScore(Object.assign({}, initial, {
      job: initial.job,
      warnings: [],
      candidate_name: ''
    }));
  }

  /* ------------------------------------------------------------------ */
  /* Events                                                              */
  /* ------------------------------------------------------------------ */
  descEl.addEventListener('input', updateCounter);

  descEl.addEventListener('keydown', function (event) {
    if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') {
      form.requestSubmit();
    }
  });

  function fillSample() {
    if (!sample) { return; }
    titleEl.value = sample.title || '';
    companyEl.value = sample.company || '';
    urlEl.value = sample.url || '';
    descEl.value = sample.description || '';
    updateCounter();
    descEl.focus();
    RI.toast('Sample internship posting pasted. Review it, then analyse.', 'info', 'Sample job loaded');
  }

  [loadSampleBtn, emptyLoadSample].forEach(function (button) {
    if (button) { button.addEventListener('click', fillSample); }
  });

  fetchBtn.addEventListener('click', async function () {
    const url = urlEl.value.trim();
    setFetchNote('');
    if (!url) {
      setFetchNote('Enter a job posting URL first, or paste the description.', 'error');
      return;
    }
    RI.setBusy(fetchBtn, true);
    try {
      const data = await RI.api('/api/jobs/fetch', { method: 'POST', body: { url: url } });
      descEl.value = data.text || '';
      if (!titleEl.value && data.page_title) {
        titleEl.value = data.page_title.split('|')[0].split('—')[0].trim().slice(0, 120);
      }
      urlEl.value = data.final_url || url;
      updateCounter();
      setFetchNote('Page text imported (' + (data.text || '').length + ' characters). Review it before analysing.', 'ok');
      RI.toast('Job page imported. Check that the description section came through clearly.', 'success', 'Page fetched');
    } catch (error) {
      setFetchNote(error.message + ' Open the posting in your browser and paste the description instead.', 'error');
      RI.toast(error.message, 'error', 'Could not fetch the page');
    } finally {
      RI.setBusy(fetchBtn, false);
    }
  });

  form.addEventListener('submit', async function (event) {
    event.preventDefault();
    const description = descEl.value.trim();
    if (description.length < 40) {
      RI.toast('Paste at least a few lines of the job description (40+ characters).', 'error', 'Description too short');
      descEl.focus();
      return;
    }
    RI.setBusy(analyzeBtn, true);
    showLoading();
    try {
      const data = await RI.api('/api/jobs/analyze', {
        method: 'POST',
        body: {
          title: titleEl.value.trim(),
          company: companyEl.value.trim(),
          url: urlEl.value.trim(),
          description: description
        }
      });
      activeJobId = data.job_id;
      results.innerHTML = renderScore(data);
      if (window.history && window.history.replaceState) {
        window.history.replaceState({}, '', '/matcher/' + data.job_id);
      }
      RI.toast('Match calculated from your saved profile.', 'success', 'Analysis complete');
      if (window.innerWidth < 1100) {
        results.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }
    } catch (error) {
      showError(error.message);
      RI.toast(error.message, 'error', 'Could not analyse');
    } finally {
      RI.setBusy(analyzeBtn, false);
    }
  });

  results.addEventListener('click', async function (event) {
    const button = event.target.closest('[data-match-action="build"]');
    if (!button) { return; }
    if (!activeJobId) {
      RI.toast('Analyse a job description first.', 'error');
      return;
    }
    RI.setBusy(button, true);
    try {
      const data = await RI.api('/api/resumes', { method: 'POST', body: { job_id: activeJobId } });
      window.location.href = data.redirect + '?job=' + encodeURIComponent(activeJobId);
    } catch (error) {
      RI.setBusy(button, false);
      if (error.data && error.data.needs_profile) {
        RI.toast('Your master profile is empty. Add your details or load the demonstration data first.', 'error', 'Profile required');
      } else {
        RI.toast(error.message, 'error', 'Could not create the draft');
      }
    }
  });

  updateCounter();
  renderInitial();
})();
