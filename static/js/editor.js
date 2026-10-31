/* ResumeIQ — interactive resume editor: autosave, undo/redo, live preview, AI tray. */
(function () {
  'use strict';

  const RI = window.RI;
  const root = document.getElementById('builderRoot');
  if (!root) { return; }

  const dataNode = document.getElementById('builderData');
  let resume = null;
  try { resume = JSON.parse(dataNode.textContent || 'null'); } catch (error) { resume = null; }
  if (!resume) { return; }

  let jobs = [];
  let meta = {};
  try { jobs = JSON.parse(document.getElementById('builderJobs').textContent || '[]'); } catch (error) { jobs = []; }
  try { meta = JSON.parse(document.getElementById('builderMeta').textContent || '{}'); } catch (error) { meta = {}; }

  const esc = RI.escapeHtml;
  const sectionList = document.getElementById('sectionList');
  const previewScaler = document.getElementById('previewScaler');
  const previewInner = document.getElementById('previewInner');
  const previewStage = document.getElementById('previewStage');
  const saveStateEl = document.getElementById('saveState');
  const titleInput = document.getElementById('builderTitle');
  const templateSelect = document.getElementById('templateSelect');
  const undoBtn = document.getElementById('undoBtn');
  const redoBtn = document.getElementById('redoBtn');
  const aiResults = document.getElementById('aiResults');
  const aiBanner = document.getElementById('aiBanner');
  const aiGenerate = document.getElementById('aiGenerate');
  const aiJobSelect = document.getElementById('aiJobSelect');
  const scaleLabel = document.getElementById('previewScaleLabel');

  function emptyDoc() {
    return {
      basics: {}, summary: '', skills: [], education: [], projects: [],
      experience: [], certifications: [], achievements: [], custom_sections: []
    };
  }

  function withDefaults(doc) {
    const base = emptyDoc();
    const merged = Object.assign(base, doc || {});
    merged.basics = Object.assign({}, doc && doc.basics ? doc.basics : {});
    ['skills', 'education', 'projects', 'experience', 'certifications', 'achievements', 'custom_sections'].forEach(function (key) {
      if (!Array.isArray(merged[key])) { merged[key] = []; }
    });
    return merged;
  }

  function normaliseSections(sections, doc) {
    let list = Array.isArray(sections) ? sections.map(function (section) {
      return {
        section_key: section.section_key,
        label: section.label || RI.SECTION_LABELS[section.section_key] || section.section_key,
        visible: section.visible !== false
      };
    }).filter(function (section) { return section.section_key; }) : [];
    if (!list.length) {
      list = RI.defaultSections().map(function (section) {
        let visible = true;
        if (section.section_key === 'certifications') { visible = (doc.certifications || []).length > 0; }
        if (section.section_key === 'achievements') { visible = (doc.achievements || []).length > 0; }
        if (section.section_key === 'summary') { visible = Boolean((doc.summary || '').trim()); }
        return Object.assign({}, section, { visible: visible });
      });
    }
    (doc.custom_sections || []).forEach(function (custom) {
      const key = 'custom:' + custom.id;
      if (!list.some(function (section) { return section.section_key === key; })) {
        list.push({ section_key: key, label: custom.title || 'Custom section', visible: true });
      }
    });
    return list;
  }

  const state = {
    id: resume.id,
    title: resume.title || 'Untitled resume',
    template: resume.template || 'classic',
    doc: withDefaults(resume.content),
    sections: normaliseSections(resume.sections, withDefaults(resume.content)),
    mobile: false,
    dirty: false,
    history: [],
    index: -1,
    lastError: '',
    ai: null
  };

  /* ------------------------------------------------------------------ */
  /* Save state + autosave                                               */
  /* ------------------------------------------------------------------ */
  function setSaveState(kind, detail) {
    if (!saveStateEl) { return; }
    saveStateEl.classList.remove('is-dirty', 'is-error');
    if (kind === 'dirty') {
      saveStateEl.classList.add('is-dirty');
      saveStateEl.innerHTML = '<span class="dot"></span> Unsaved changes';
    } else if (kind === 'saving') {
      saveStateEl.classList.add('is-dirty');
      saveStateEl.innerHTML = '<span class="dot"></span> Saving…';
    } else if (kind === 'error') {
      saveStateEl.classList.add('is-error');
      saveStateEl.innerHTML = '<span class="dot"></span> Save failed — retrying on next edit';
      saveStateEl.title = detail || '';
    } else {
      const when = detail ? new Date(String(detail).replace(' ', 'T') + 'Z') : null;
      const label = when && !Number.isNaN(when.getTime())
        ? 'Saved ' + when.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
        : 'All changes saved';
      saveStateEl.innerHTML = '<span class="dot"></span> ' + esc(label);
      saveStateEl.title = '';
    }
  }

  function snapshot() {
    return JSON.stringify({
      doc: state.doc,
      sections: state.sections,
      title: state.title,
      template: state.template
    });
  }

  function recordHistory() {
    const serialised = snapshot();
    if (state.history[state.index] === serialised) { return; }
    state.history = state.history.slice(0, state.index + 1);
    state.history.push(serialised);
    if (state.history.length > 60) { state.history.shift(); }
    state.index = state.history.length - 1;
    updateHistoryButtons();
  }

  const scheduleHistory = RI.debounce(recordHistory, 650);

  function updateHistoryButtons() {
    undoBtn.disabled = state.index <= 0;
    redoBtn.disabled = state.index >= state.history.length - 1;
  }

  function applySnapshot(serialised) {
    const snap = JSON.parse(serialised);
    state.doc = snap.doc;
    state.sections = snap.sections;
    state.title = snap.title;
    state.template = snap.template;
    if (titleInput) { titleInput.value = state.title; }
    if (templateSelect) { templateSelect.value = state.template; }
    renderSections();
    renderPreview();
    markDirty();
    updateHistoryButtons();
  }

  function undo() {
    if (state.index <= 0) { return; }
    state.index -= 1;
    applySnapshot(state.history[state.index]);
  }
  function redo() {
    if (state.index >= state.history.length - 1) { return; }
    state.index += 1;
    applySnapshot(state.history[state.index]);
  }

  let saveChain = Promise.resolve();

  async function saveOnce() {
    if (!state.dirty) { return; }
    setSaveState('saving');
    try {
      const response = await RI.api('/api/resumes/' + state.id, {
        method: 'PUT',
        body: {
          title: state.title,
          template: state.template,
          content: state.doc,
          sections: state.sections
        }
      });
      state.dirty = false;
      state.lastError = '';
      setSaveState('saved', response && response.saved_at);
    } catch (error) {
      state.dirty = true;
      setSaveState('error', error.message);
      if (state.lastError !== error.message) {
        state.lastError = error.message;
        RI.toast(error.message, 'error', 'Autosave failed');
      }
    }
  }

  function queueSave() {
    saveChain = saveChain.then(saveOnce).catch(function () {});
    return saveChain;
  }
  const scheduleSave = RI.debounce(queueSave, 850);

  function markDirty() {
    state.dirty = true;
    setSaveState('dirty');
    scheduleSave();
  }

  async function flushSave() {
    scheduleSave.cancel();
    scheduleHistory.flush();
    await queueSave();
    return !state.dirty;
  }

  /* ------------------------------------------------------------------ */
  /* Preview                                                            */
  /* ------------------------------------------------------------------ */
  function renderPreview() {
    previewScaler.innerHTML = RI.renderResume(state.doc, state.template, {
      sections: state.sections,
      mobile: state.mobile
    });
    requestAnimationFrame(updateScale);
  }

  function updateScale() {
    const paper = previewScaler.querySelector('.resume-paper');
    if (!paper) { return; }
    const paperWidth = state.mobile ? 390 : 794;
    const stageWidth = Math.max(240, previewStage.clientWidth - 34);
    const scale = Math.min(1, stageWidth / paperWidth);
    previewScaler.style.transform = 'scale(' + scale + ')';
    previewScaler.style.width = paperWidth + 'px';
    previewInner.style.width = Math.round(paperWidth * scale) + 'px';
    previewInner.style.height = Math.round(paper.offsetHeight * scale) + 'px';
    if (scaleLabel) {
      scaleLabel.textContent = state.mobile ? 'Mobile · ' + Math.round(scale * 100) + '%' : 'A4 · ' + Math.round(scale * 100) + '%';
    }
  }

  /* ------------------------------------------------------------------ */
  /* Editor rendering                                                   */
  /* ------------------------------------------------------------------ */
  const SECTION_HINTS = {
    summary: 'Two or three factual sentences, tailored to this role.',
    skills: 'Only skills you can defend in an interview.',
    education: 'Most recent first.',
    projects: 'Lead with an action verb and the outcome.',
    experience: 'What you owned, built or improved.',
    certifications: 'Name, issuer and year.',
    achievements: 'Awards, contests, measurable milestones.'
  };

  function field(label, path, value, options) {
    const opts = options || {};
    const type = opts.type || 'text';
    const control = opts.textarea
      ? '<textarea class="textarea" rows="' + (opts.rows || 3) + '" data-path="' + path + '" maxlength="' + (opts.max || 3000) + '" placeholder="' + esc(opts.placeholder || '') + '">' + esc(value) + '</textarea>'
      : '<input class="input" type="' + type + '" data-path="' + path + '" maxlength="' + (opts.max || 200) + '" value="' + esc(value) + '" placeholder="' + esc(opts.placeholder || '') + '">';
    return '<div class="field' + (opts.span ? ' span-2' : '') + '">' +
      '<label>' + esc(label) + '</label>' + control +
      (opts.hint ? '<p class="field-hint">' + esc(opts.hint) + '</p>' : '') + '</div>';
  }

  function bulletEditor(basePath, bullets, targetKey, entryIndex) {
    const rows = (bullets || []).map(function (bullet, bulletIndex) {
      return '<div class="bullet-row">' +
        '<input class="input" data-path="' + basePath + '.bullets.' + bulletIndex + '" maxlength="600" value="' + esc(bullet) + '" placeholder="Describe an action and its result">' +
        '<div class="bullet-tools">' +
          '<button class="icon-mini" type="button" title="Move bullet up" data-move-bullet="up" data-target="' + targetKey + '" data-entry="' + entryIndex + '" data-index="' + bulletIndex + '" ' + (bulletIndex === 0 ? 'disabled' : '') + '>↑</button>' +
          '<button class="icon-mini" type="button" title="Move bullet down" data-move-bullet="down" data-target="' + targetKey + '" data-entry="' + entryIndex + '" data-index="' + bulletIndex + '" ' + (bulletIndex === (bullets || []).length - 1 ? 'disabled' : '') + '>↓</button>' +
          '<button class="icon-mini is-danger" type="button" title="Delete bullet" data-remove-bullet="' + targetKey + '" data-entry="' + entryIndex + '" data-index="' + bulletIndex + '">×</button>' +
        '</div></div>';
    }).join('');
    return '<div class="bullet-list">' + (rows || '<p class="bullet-hint">No bullet points yet.</p>') + '</div>' +
      '<button class="link-btn" type="button" data-add-bullet="' + targetKey + '" data-entry="' + entryIndex + '">+ Add bullet point</button>';
  }

  function educationBody(items) {
    if (!items.length) {
      return '<p class="editor-empty-note">No education entries yet.</p>' +
        '<button class="link-btn" type="button" data-add-entry="education">+ Add education</button>';
    }
    return items.map(function (item, index) {
      return '<div class="entry-edit-card">' +
        '<div class="entry-edit-head"><strong>Education ' + (index + 1) + '</strong>' +
        '<button class="link-btn is-danger" type="button" data-remove-entry="education" data-index="' + index + '">Remove</button></div>' +
        '<div class="field-grid">' +
        field('Institution', 'education.' + index + '.institution', item.institution, { placeholder: 'Vellore Institute of Technology', max: 160 }) +
        field('Degree', 'education.' + index + '.degree', item.degree, { placeholder: 'B.Tech', max: 120 }) +
        field('Field', 'education.' + index + '.field', item.field, { placeholder: 'Computer Science', max: 120 }) +
        field('Score', 'education.' + index + '.score', item.score, { placeholder: 'CGPA 8.7/10', max: 60 }) +
        field('Start', 'education.' + index + '.start_date', item.start_date, { placeholder: '2021', max: 40 }) +
        field('End', 'education.' + index + '.end_date', item.end_date, { placeholder: '2025', max: 40 }) +
        field('Location', 'education.' + index + '.location', item.location, { placeholder: 'Vellore, India', max: 120, span: true }) +
        '</div></div>';
    }).join('') +
      '<button class="link-btn" type="button" data-add-entry="education">+ Add education</button>';
  }

  function projectBody(items) {
    const entries = items.map(function (item, index) {
      return '<div class="entry-edit-card">' +
        '<div class="entry-edit-head"><strong>' + esc(item.name || 'Project ' + (index + 1)) + '</strong>' +
        '<button class="link-btn is-danger" type="button" data-remove-entry="projects" data-index="' + index + '">Remove</button></div>' +
        '<div class="field-grid">' +
        field('Name', 'projects.' + index + '.name', item.name, { placeholder: 'CampusConnect', max: 160 }) +
        field('Tech stack', 'projects.' + index + '.tech', item.tech, { placeholder: 'React, Node.js', max: 220 }) +
        field('Link', 'projects.' + index + '.link', item.link, { placeholder: 'https://github.com/...', max: 300, span: true }) +
        '</div>' +
        '<span class="mini-label" style="margin:2px 0 0;">Bullet points</span>' +
        bulletEditor('projects.' + index, item.bullets, 'projects', index) +
        '</div>';
    }).join('');
    return (entries || '<p class="editor-empty-note">No projects yet.</p>') +
      '<button class="link-btn" type="button" data-add-entry="projects">+ Add project</button>';
  }

  function experienceBody(items) {
    const entries = items.map(function (item, index) {
      return '<div class="entry-edit-card">' +
        '<div class="entry-edit-head"><strong>' + esc(item.role || 'Experience ' + (index + 1)) + '</strong>' +
        '<button class="link-btn is-danger" type="button" data-remove-entry="experience" data-index="' + index + '">Remove</button></div>' +
        '<div class="field-grid">' +
        field('Role', 'experience.' + index + '.role', item.role, { placeholder: 'Backend Developer Intern', max: 160 }) +
        field('Company', 'experience.' + index + '.company', item.company, { placeholder: 'Zeta Innovations', max: 160 }) +
        field('Start', 'experience.' + index + '.start_date', item.start_date, { placeholder: 'May 2024', max: 40 }) +
        field('End', 'experience.' + index + '.end_date', item.end_date, { placeholder: 'Jul 2024', max: 40 }) +
        field('Location', 'experience.' + index + '.location', item.location, { placeholder: 'Bengaluru, India', max: 120, span: true }) +
        '</div>' +
        '<span class="mini-label" style="margin:2px 0 0;">Bullet points</span>' +
        bulletEditor('experience.' + index, item.bullets, 'experience', index) +
        '</div>';
    }).join('');
    return (entries || '<p class="editor-empty-note">No experience yet.</p>') +
      '<button class="link-btn" type="button" data-add-entry="experience">+ Add experience</button>';
  }

  function certificationBody(items) {
    const entries = items.map(function (item, index) {
      return '<div class="entry-edit-card">' +
        '<div class="entry-edit-head"><strong>' + esc(item.name || 'Certification ' + (index + 1)) + '</strong>' +
        '<button class="link-btn is-danger" type="button" data-remove-entry="certifications" data-index="' + index + '">Remove</button></div>' +
        '<div class="field-grid three">' +
        field('Name', 'certifications.' + index + '.name', item.name, { placeholder: 'AWS Cloud Practitioner', max: 180 }) +
        field('Issuer', 'certifications.' + index + '.issuer', item.issuer, { placeholder: 'Amazon Web Services', max: 160 }) +
        field('Year', 'certifications.' + index + '.year', item.year, { placeholder: '2024', max: 20 }) +
        '</div></div>';
    }).join('');
    return (entries || '<p class="editor-empty-note">No certifications yet.</p>') +
      '<button class="link-btn" type="button" data-add-entry="certifications">+ Add certification</button>';
  }

  function achievementBody(items) {
    const rows = items.map(function (text, index) {
      return '<div class="bullet-row">' +
        '<input class="input" data-path="achievements.' + index + '" maxlength="400" value="' + esc(text) + '" placeholder="Finalist, Smart India Hackathon 2024">' +
        '<div class="bullet-tools">' +
          '<button class="icon-mini" type="button" title="Move up" data-move-bullet="up" data-target="achievements" data-index="' + index + '" ' + (index === 0 ? 'disabled' : '') + '>↑</button>' +
          '<button class="icon-mini" type="button" title="Move down" data-move-bullet="down" data-target="achievements" data-index="' + index + '" ' + (index === items.length - 1 ? 'disabled' : '') + '>↓</button>' +
          '<button class="icon-mini is-danger" type="button" title="Delete" data-remove-bullet="achievements" data-index="' + index + '">×</button>' +
        '</div></div>';
    }).join('');
    return '<div class="bullet-list">' + (rows || '<p class="bullet-hint">No achievements yet.</p>') + '</div>' +
      '<button class="link-btn" type="button" data-add-bullet="achievements">+ Add achievement</button>';
  }

  function skillsBody() {
    const tags = (state.doc.skills || []).map(function (skill, index) {
      return '<span class="tag">' + esc(skill) +
        '<button type="button" aria-label="Remove ' + esc(skill) + '" data-remove-skill="' + index + '">×</button></span>';
    }).join('');
    return '<div class="chip-input" data-skill-wrap>' +
      '<div class="chips-row" data-skill-tags>' + tags + '</div>' +
      '<input class="chip-input-field" data-skill-input maxlength="60" placeholder="Add a skill and press Enter" aria-label="Add a skill">' +
      '</div><p class="field-hint">Skill order is preserved in the preview and both exports.</p>';
  }

  function customBody(customId) {
    const custom = (state.doc.custom_sections || []).find(function (item) { return item.id === customId; });
    if (!custom) { return '<p class="editor-empty-note">This section no longer exists.</p>'; }
    return '<div class="field"><label>Section title</label>' +
      '<input class="input" data-custom-title="' + esc(customId) + '" maxlength="80" value="' + esc(custom.title) + '"></div>' +
      bulletEditor('custom_sections.' + (state.doc.custom_sections || []).indexOf(custom), custom.bullets, 'custom:' + customId, 0);
  }

  function sectionBody(key) {
    if (key === 'summary') {
      return '<div class="field"><label>Professional summary</label>' +
        '<textarea class="textarea" rows="4" data-path="summary" maxlength="2500" placeholder="Two or three sentences tailored to this job.">' + esc(state.doc.summary) + '</textarea>' +
        '<p class="field-hint">Only facts already true about you — the AI validator blocks new skills and metrics here.</p></div>';
    }
    if (key === 'skills') { return skillsBody(); }
    if (key === 'education') { return educationBody(state.doc.education || []); }
    if (key === 'projects') { return projectBody(state.doc.projects || []); }
    if (key === 'experience') { return experienceBody(state.doc.experience || []); }
    if (key === 'certifications') { return certificationBody(state.doc.certifications || []); }
    if (key === 'achievements') { return achievementBody(state.doc.achievements || []); }
    if (key.indexOf('custom:') === 0) { return customBody(key.slice(7)); }
    return '';
  }

  function renderSections() {
    if (!sectionList) { return; }
    sectionList.innerHTML = state.sections.map(function (section, index) {
      const key = section.section_key;
      const isCustom = key.indexOf('custom:') === 0;
      const label = section.label || RI.SECTION_LABELS[key] || 'Section';
      return '<section class="section-card ' + (section.visible ? '' : 'is-hidden-section') + '" draggable="true" data-section-key="' + esc(key) + '" data-index="' + index + '">' +
        '<header class="section-head">' +
          '<span class="drag-handle" title="Drag to reorder" aria-hidden="true">⠿</span>' +
          '<span class="section-order-num">' + (index + 1) + '</span>' +
          '<div class="section-head-text"><strong>' + esc(label) + '</strong>' +
            '<small>' + esc(SECTION_HINTS[key] || 'Custom section — bullets only.') + '</small></div>' +
          '<div class="section-controls">' +
            '<button class="icon-mini" type="button" title="Move section up" data-move-section="up" data-index="' + index + '" ' + (index === 0 ? 'disabled' : '') + '>↑</button>' +
            '<button class="icon-mini" type="button" title="Move section down" data-move-section="down" data-index="' + index + '" ' + (index === state.sections.length - 1 ? 'disabled' : '') + '>↓</button>' +
            '<label class="switch" title="Show in preview and exports">' +
              '<input type="checkbox" data-toggle-section="' + index + '" ' + (section.visible ? 'checked' : '') + ' aria-label="Show ' + esc(label) + '">' +
              '<span class="switch-track"></span>' +
            '</label>' +
            (isCustom ? '<button class="icon-mini is-danger" type="button" title="Delete section" data-delete-section="' + index + '">×</button>' : '') +
          '</div>' +
        '</header>' +
        '<div class="editor-body">' + sectionBody(key) + '</div>' +
      '</section>';
    }).join('');
  }

  /* ------------------------------------------------------------------ */
  /* Editing events                                                     */
  /* ------------------------------------------------------------------ */
  function touch(value, path) {
    RI.pathSet(state.doc, path, value);
    renderPreview();
    markDirty();
    scheduleHistory();
    scheduleSave();
  }

  if (sectionList) {
    sectionList.addEventListener('input', function (event) {
      const pathInput = event.target.closest('[data-path]');
      if (pathInput) {
        touch(pathInput.value, pathInput.dataset.path);
        return;
      }
      const titleField = event.target.closest('[data-custom-title]');
      if (titleField) {
        const id = titleField.dataset.customTitle;
        const custom = (state.doc.custom_sections || []).find(function (item) { return item.id === id; });
        if (custom) {
          custom.title = titleField.value;
          const section = state.sections.find(function (item) { return item.section_key === 'custom:' + id; });
          if (section) { section.label = titleField.value || 'Custom section'; }
          renderPreview();
          markDirty();
          scheduleHistory();
          scheduleSave();
        }
      }
    });

    sectionList.addEventListener('keydown', function (event) {
      const skillInput = event.target.closest('[data-skill-input]');
      if (!skillInput) { return; }
      if (event.key === 'Enter' || event.key === ',') {
        event.preventDefault();
        addSkill(skillInput.value);
      }
    });

    sectionList.addEventListener('focusout', function (event) {
      const titleField = event.target.closest('[data-custom-title]');
      if (titleField) { renderSections(); }
    });

    sectionList.addEventListener('click', function (event) {
      const target = event.target;

      const removeSkill = target.closest('[data-remove-skill]');
      if (removeSkill) {
        state.doc.skills.splice(Number(removeSkill.dataset.removeSkill), 1);
        renderSections();
        afterStructureChange();
        return;
      }

      const addEntry = target.closest('[data-add-entry]');
      if (addEntry) {
        const type = addEntry.dataset.addEntry;
        if (type === 'education') { state.doc.education.push({}); }
        if (type === 'projects') { state.doc.projects.push({ name: '', tech: '', link: '', bullets: [''] }); }
        if (type === 'experience') { state.doc.experience.push({ role: '', company: '', start_date: '', end_date: '', location: '', bullets: [''] }); }
        if (type === 'certifications') { state.doc.certifications.push({}); }
        renderSections();
        afterStructureChange();
        return;
      }

      const removeEntry = target.closest('[data-remove-entry]');
      if (removeEntry) {
        const type = removeEntry.dataset.removeEntry;
        const index = Number(removeEntry.dataset.index);
        if (Array.isArray(state.doc[type])) {
          state.doc[type].splice(index, 1);
          renderSections();
          afterStructureChange();
        }
        return;
      }

      const addBullet = target.closest('[data-add-bullet]');
      if (addBullet) {
        const key = addBullet.dataset.addBullet;
        if (key === 'achievements') {
          state.doc.achievements.push('');
        } else if (key.indexOf('custom:') === 0) {
          const id = key.slice(7);
          const custom = (state.doc.custom_sections || []).find(function (item) { return item.id === id; });
          if (custom) { custom.bullets = custom.bullets || []; custom.bullets.push(''); }
        } else {
          const entry = state.doc[key][Number(addBullet.dataset.entry)];
          if (entry) {
            entry.bullets = entry.bullets || [];
            entry.bullets.push('');
          }
        }
        renderSections();
        afterStructureChange();
        return;
      }

      const removeBullet = target.closest('[data-remove-bullet]');
      if (removeBullet) {
        const key = removeBullet.dataset.removeBullet;
        const index = Number(removeBullet.dataset.index);
        if (key === 'achievements') {
          state.doc.achievements.splice(index, 1);
        } else if (key.indexOf('custom:') === 0) {
          const custom = (state.doc.custom_sections || []).find(function (item) { return item.id === key.slice(7); });
          if (custom && custom.bullets) { custom.bullets.splice(index, 1); }
        } else {
          const entry = state.doc[key][Number(removeBullet.dataset.entry)];
          if (entry && entry.bullets) { entry.bullets.splice(index, 1); }
        }
        renderSections();
        afterStructureChange();
        return;
      }

      const moveBullet = target.closest('[data-move-bullet]');
      if (moveBullet) {
        const direction = moveBullet.dataset.moveBullet;
        const key = moveBullet.dataset.target;
        const index = Number(moveBullet.dataset.index);
        const newIndex = direction === 'up' ? index - 1 : index + 1;
        const list = key === 'achievements'
          ? state.doc.achievements
          : (key.indexOf('custom:') === 0
            ? (state.doc.custom_sections || []).find(function (item) { return item.id === key.slice(7); })
            : state.doc[key] && state.doc[key][Number(moveBullet.dataset.entry)]);
        const bullets = key === 'achievements' ? list : (list && list.bullets);
        if (!bullets || newIndex < 0 || newIndex >= bullets.length) { return; }
        const temp = bullets[index];
        bullets[index] = bullets[newIndex];
        bullets[newIndex] = temp;
        renderSections();
        afterStructureChange();
        return;
      }

      const moveSection = target.closest('[data-move-section]');
      if (moveSection) {
        const index = Number(moveSection.dataset.index);
        const newIndex = moveSection.dataset.moveSection === 'up' ? index - 1 : index + 1;
        if (newIndex < 0 || newIndex >= state.sections.length) { return; }
        const moved = state.sections.splice(index, 1)[0];
        state.sections.splice(newIndex, 0, moved);
        renderSections();
        afterStructureChange();
        return;
      }

      const deleteSection = target.closest('[data-delete-section]');
      if (deleteSection) {
        const index = Number(deleteSection.dataset.deleteSection);
        const section = state.sections[index];
        if (!section || section.section_key.indexOf('custom:') !== 0) { return; }
        if (!window.confirm('Delete this custom section and its bullets?')) { return; }
        const id = section.section_key.slice(7);
        state.sections.splice(index, 1);
        state.doc.custom_sections = (state.doc.custom_sections || []).filter(function (item) { return item.id !== id; });
        renderSections();
        afterStructureChange();
      }
    });

    sectionList.addEventListener('change', function (event) {
      const toggle = event.target.closest('[data-toggle-section]');
      if (toggle) {
        state.sections[Number(toggle.dataset.toggleSection)].visible = toggle.checked;
        renderSections();
        afterStructureChange();
      }
    });

    /* Drag and drop reordering */
    let dragIndex = null;
    sectionList.addEventListener('dragstart', function (event) {
      const card = event.target.closest('.section-card');
      if (!card) { return; }
      if (!event.target.closest('.drag-handle') && !event.target.closest('.section-head')) {
        event.preventDefault();
        return;
      }
      dragIndex = Number(card.dataset.index);
      card.classList.add('is-dragging');
      event.dataTransfer.effectAllowed = 'move';
      try { event.dataTransfer.setData('text/plain', String(dragIndex)); } catch (error) { /* ignore */ }
    });
    sectionList.addEventListener('dragover', function (event) {
      const card = event.target.closest('.section-card');
      if (!card || dragIndex === null) { return; }
      event.preventDefault();
      sectionList.querySelectorAll('.section-card').forEach(function (node) {
        node.classList.toggle('is-drop-target', node === card && Number(card.dataset.index) !== dragIndex);
      });
    });
    sectionList.addEventListener('dragleave', function (event) {
      const card = event.target.closest('.section-card');
      if (card) { card.classList.remove('is-drop-target'); }
    });
    sectionList.addEventListener('drop', function (event) {
      const card = event.target.closest('.section-card');
      if (!card || dragIndex === null) { return; }
      event.preventDefault();
      const targetIndex = Number(card.dataset.index);
      if (targetIndex !== dragIndex) {
        const moved = state.sections.splice(dragIndex, 1)[0];
        state.sections.splice(targetIndex, 0, moved);
        renderSections();
        afterStructureChange();
      }
      dragIndex = null;
    });
    sectionList.addEventListener('dragend', function () {
      dragIndex = null;
      sectionList.querySelectorAll('.section-card').forEach(function (node) {
        node.classList.remove('is-dragging', 'is-drop-target');
      });
    });
  }

  function addSkill(raw) {
    const value = String(raw || '').trim().replace(/\s+/g, ' ');
    if (!value) { return; }
    const exists = state.doc.skills.some(function (skill) { return skill.toLowerCase() === value.toLowerCase(); });
    if (!exists) {
      state.doc.skills.push(value);
      renderSections();
      const input = sectionList.querySelector('[data-skill-input]');
      if (input) { input.focus(); }
      afterStructureChange();
    }
  }

  function afterStructureChange() {
    renderPreview();
    recordHistory();
    markDirty();
    scheduleSave();
  }

  /* ------------------------------------------------------------------ */
  /* Toolbar events                                                     */
  /* ------------------------------------------------------------------ */
  if (titleInput) {
    titleInput.addEventListener('input', function () {
      state.title = titleInput.value;
      markDirty();
      scheduleHistory();
    });
  }
  if (templateSelect) {
    templateSelect.addEventListener('change', function () {
      state.template = templateSelect.value;
      renderPreview();
      recordHistory();
      markDirty();
    });
  }
  undoBtn.addEventListener('click', undo);
  redoBtn.addEventListener('click', redo);

  document.addEventListener('keydown', function (event) {
    if (!(event.ctrlKey || event.metaKey)) { return; }
    if (event.target.closest('input, textarea')) { return; }
    if (event.key.toLowerCase() === 'z' && !event.shiftKey) {
      event.preventDefault();
      undo();
    } else if ((event.key.toLowerCase() === 'z' && event.shiftKey) || event.key.toLowerCase() === 'y') {
      event.preventDefault();
      redo();
    }
  });

  const addSection = document.getElementById('addSection');
  if (addSection) {
    addSection.addEventListener('click', function () {
      const id = 'x' + Date.now().toString(36);
      const custom = { id: id, title: 'Additional Section', bullets: [''] };
      state.doc.custom_sections.push(custom);
      const section = { section_key: 'custom:' + id, label: custom.title, visible: true };
      const summaryIndex = state.sections.findIndex(function (item) { return item.section_key === 'summary'; });
      if (summaryIndex >= 0) { state.sections.splice(summaryIndex + 1, 0, section); } else { state.sections.push(section); }
      renderSections();
      afterStructureChange();
      RI.toast('Custom section added. Give it a title or delete it from its header.', 'info');
    });
  }

  const deleteResume = document.getElementById('deleteResume');
  if (deleteResume) {
    deleteResume.addEventListener('click', async function () {
      if (!window.confirm('Delete this resume draft permanently? Your master profile is not affected.')) { return; }
      RI.setBusy(deleteResume, true);
      try {
        await RI.api('/api/resumes/' + state.id, { method: 'DELETE' });
        window.location.href = '/builder';
      } catch (error) {
        RI.setBusy(deleteResume, false);
        RI.toast(error.message, 'error', 'Could not delete the draft');
      }
    });
  }

  /* Export: always flush the latest edits first */
  document.querySelectorAll('[data-export]').forEach(function (link) {
    link.addEventListener('click', async function (event) {
      event.preventDefault();
      const href = link.getAttribute('href');
      RI.setBusy(link, true);
      try {
        const saved = await flushSave();
        if (!saved) {
          RI.toast('Export blocked because the latest changes could not be saved. Retry once the save succeeds.', 'error', 'Not exported');
          return;
        }
        window.location.href = href;
      } finally {
        setTimeout(function () { RI.setBusy(link, false); }, 1500);
      }
    });
  });

  /* Device preview toggle */
  document.querySelectorAll('[data-device]').forEach(function (button) {
    button.addEventListener('click', function () {
      document.querySelectorAll('[data-device]').forEach(function (node) { node.classList.remove('is-active'); });
      button.classList.add('is-active');
      state.mobile = button.dataset.device === 'mobile';
      renderPreview();
    });
  });

  window.addEventListener('resize', function () { requestAnimationFrame(updateScale); });
  window.addEventListener('beforeunload', function (event) {
    if (state.dirty) {
      event.preventDefault();
      event.returnValue = '';
    }
  });

  /* ------------------------------------------------------------------ */
  /* AI tailoring                                                       */
  /* ------------------------------------------------------------------ */
  function aiBannerMessage(kind, text) {
    aiBanner.innerHTML = '<div class="ai-mode-banner ' + kind + '">' + text + '</div>';
  }

  function aiApplyButton(label, attribute, value, extraClass) {
    return '<button class="btn btn-sm ' + (extraClass || 'btn-primary') + '" type="button" ' + attribute + '="' + esc(value) + '">' + esc(label) + '</button>';
  }

  function renderAiSuggestions(payload) {
    const pieces = [];
    if (payload.summary) {
      const level = payload.summary.status === 'ready' ? 'chip-good' : 'chip-warn';
      pieces.push('<div class="ai-suggestion" data-ai-card="summary">' +
        '<div class="ai-suggestion-head"><strong>Tailored professional summary</strong>' +
        '<span class="chip ' + level + '">' + (payload.summary.status === 'ready' ? 'Ready for review' : 'Needs your confirmation') + '</span></div>' +
        '<p class="ai-improved">' + esc(payload.summary.text) + '</p>' +
        (payload.summary.rationale ? '<p class="ai-rationale">' + esc(payload.summary.rationale) + '</p>' : '') +
        ((payload.summary.issues || []).length
          ? '<div class="ai-issues">' + payload.summary.issues.map(esc).join('<br>') + '</div>' : '') +
        '<div class="ai-actions">' +
          aiApplyButton('Apply to summary', 'data-ai-apply', 'summary') +
          '<button class="btn btn-ghost btn-sm" type="button" data-ai-dismiss>Dismiss</button>' +
        '</div></div>');
    }

    (payload.bullet_improvements || []).forEach(function (suggestion, index) {
      pieces.push('<div class="ai-suggestion" data-ai-card="bullet" data-ai-index="' + index + '">' +
        '<div class="ai-suggestion-head"><strong>' + esc(suggestion.location || 'Bullet rewrite') + '</strong>' +
        '<span class="chip chip-warn">Requires confirmation</span></div>' +
        '<div class="ai-original">' + esc(suggestion.original) + '</div>' +
        '<div class="ai-improved">' + esc(suggestion.improved) + '</div>' +
        (suggestion.rationale ? '<p class="ai-rationale">' + esc(suggestion.rationale) + '</p>' : '') +
        '<div class="ai-actions">' +
          aiApplyButton('Apply rewrite', 'data-ai-apply', 'bullet:' + index) +
          '<button class="btn btn-ghost btn-sm" type="button" data-ai-dismiss>Dismiss</button>' +
        '</div></div>');
    });

    if (!pieces.length) {
      pieces.push('<p class="ai-empty">No safe rewrites were produced for this draft. Add more detail to your bullets and try again.</p>');
    }

    if ((payload.keywords || []).length) {
      const present = payload.keywords.filter(function (item) { return item.present_in_profile; });
      const absent = payload.keywords.filter(function (item) { return !item.present_in_profile; });
      pieces.push('<div class="ai-suggestion"><div class="ai-suggestion-head"><strong>Suggested keywords</strong>' +
        '<span class="chip chip-ghost">Informational</span></div>' +
        (present.length ? '<span class="mini-label">Already in your profile</span><div class="ai-keywords">' +
          present.map(function (item) { return '<span class="chip chip-good">' + esc(item.keyword) + '</span>'; }).join('') + '</div>' : '') +
        (absent.length ? '<span class="mini-label" style="margin-top:8px;">Not in your profile — do not add unless true</span><div class="ai-keywords">' +
          absent.map(function (item) { return '<span class="chip chip-warn" title="' + esc(item.note) + '">' + esc(item.keyword) + '</span>'; }).join('') + '</div>' : '') +
        '</div>');
    }

    if ((payload.action_verbs || []).length) {
      pieces.push('<div class="ai-suggestion"><div class="ai-suggestion-head"><strong>Stronger action verbs</strong>' +
        '<span class="chip chip-ghost">Vocabulary only</span></div>' +
        '<div class="verbs-row">' + payload.action_verbs.map(function (verb) {
          return '<span class="chip chip-soft">' + esc(verb) + '</span>';
        }).join('') + '</div></div>');
    }

    if ((payload.rejected || []).length) {
      pieces.push('<details class="ai-rejected"><summary>' + payload.rejected.length +
        ' suggestion(s) rejected by the fabrication guard</summary><ul>' +
        payload.rejected.map(function (item) {
          return '<li><strong>' + esc(item.location || 'Suggestion') + '</strong><br>' + esc(item.reason) +
            (item.improved ? '<br><span class="source-note">' + esc(item.improved) + '</span>' : '') + '</li>';
        }).join('') + '</ul></details>');
    }

    if ((payload.notes || []).length) {
      pieces.push('<div class="ai-suggestion"><div class="ai-suggestion-head"><strong>Notes</strong></div>' +
        '<ul class="detail-list">' + payload.notes.map(function (note) { return '<li>' + esc(note) + '</li>'; }).join('') + '</ul></div>');
    }

    pieces.push('<p class="disclaimer">' + esc(payload.disclaimer || '') + '</p>');
    aiResults.innerHTML = pieces.join('');
    state.ai = payload;
  }

  async function generateSuggestions() {
    const jobId = aiJobSelect && aiJobSelect.value;
    if (!jobId) {
      RI.toast('Analyse a job description first so there is something to tailor against.', 'error');
      return;
    }
    RI.setBusy(aiGenerate, true);
    aiResults.innerHTML = '<div class="loading-block"><div class="spinner"></div><span>Comparing your draft with the job requirements…</span></div>';
    aiBanner.innerHTML = '';
    try {
      const data = await RI.api('/api/resumes/' + state.id + '/tailor', {
        method: 'POST',
        body: { job_id: Number(jobId) }
      });
      const payload = data.tailoring;
      if (payload.live) {
        aiBannerMessage('is-live', '<strong>Live AI:</strong> ' + esc(payload.reason || 'Generated by Featherless AI.') +
          ' Every suggestion still needs your confirmation.');
      } else {
        aiBannerMessage('is-fallback', '<strong>No live AI used.</strong> ' + esc(payload.reason || 'Deterministic fallback.') +
          (payload.error ? '<br><span class="source-note">' + esc(payload.error) + '</span>' : ''));
      }
      renderAiSuggestions(payload);
    } catch (error) {
      aiBannerMessage('is-error', '<strong>Tailoring failed.</strong> ' + esc(error.message));
      aiResults.innerHTML = '<div class="ai-empty">You can keep editing manually — nothing was changed. ' +
        'If the AI service is unavailable, deterministic matching on the Job Matcher page still works.</div>';
      RI.toast(error.message, 'error', 'AI tailoring failed');
    } finally {
      RI.setBusy(aiGenerate, false);
    }
  }

  if (aiGenerate) { aiGenerate.addEventListener('click', generateSuggestions); }

  if (aiResults) {
    aiResults.addEventListener('click', function (event) {
      const dismiss = event.target.closest('[data-ai-dismiss]');
      if (dismiss) {
        const card = dismiss.closest('[data-ai-card]');
        if (card) { card.remove(); }
        return;
      }
      const apply = event.target.closest('[data-ai-apply]');
      if (apply) {
        const value = apply.dataset.aiApply;
        if (!state.ai) { return; }
        if (value === 'summary') {
          if (!state.ai.summary) { return; }
          state.doc.summary = state.ai.summary.text;
          const card = apply.closest('[data-ai-card]');
          if (card) { card.remove(); }
          renderSections();
          afterStructureChange();
          RI.toast('Summary applied. Edit it in the editor and check every claim is true.', 'success', 'Applied');
          return;
        }
        if (value.indexOf('bullet:') === 0) {
          const index = Number(value.split(':')[1]);
          const suggestion = state.ai.bullet_improvements[index];
          if (!suggestion) { return; }
          const listKey = suggestion.target === 'project' ? 'projects' : 'experience';
          const entry = state.doc[listKey][suggestion.index];
          if (!entry) { return; }
          entry.bullets = entry.bullets || [];
          const normalise = function (text) { return String(text || '').trim().toLowerCase().replace(/\s+/g, ' '); };
          let targetEntry = entry;
          let bulletIndex = entry.bullets.findIndex(function (bullet) {
            return normalise(bullet) === normalise(suggestion.original);
          });
          if (bulletIndex === -1) {
            for (let i = 0; i < state.doc[listKey].length; i += 1) {
              const candidate = state.doc[listKey][i];
              const found = (candidate.bullets || []).findIndex(function (bullet) {
                return normalise(bullet) === normalise(suggestion.original);
              });
              if (found !== -1) { bulletIndex = found; targetEntry = candidate; break; }
            }
          }
          if (bulletIndex === -1) {
            RI.toast('That bullet was edited after the suggestion was generated. Generate suggestions again.', 'error');
            return;
          }
          targetEntry.bullets[bulletIndex] = suggestion.improved;
          const card = apply.closest('[data-ai-card]');
          if (card) { card.remove(); }
          renderSections();
          afterStructureChange();
          RI.toast('Rewrite applied. Confirm it matches your actual work.', 'success', 'Applied');
        }
      }
    });
  }

  /* ------------------------------------------------------------------ */
  /* Init                                                               */
  /* ------------------------------------------------------------------ */
  renderSections();
  renderPreview();
  recordHistory();
  setSaveState('saved');
  const requestedJob = Number(meta.requestedJobId || 0);
  if (requestedJob && aiJobSelect) {
    aiJobSelect.value = String(requestedJob);
    if (!aiJobSelect.value) {
      Array.prototype.slice.call(aiJobSelect.options).forEach(function (option) {
        if (option.value === String(requestedJob)) { option.selected = true; }
      });
    }
  }
})();
