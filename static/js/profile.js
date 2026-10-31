/* ResumeIQ — master profile editor (repeating entries, skills, validation). */
(function () {
  'use strict';

  const RI = window.RI;
  const form = document.getElementById('profileForm');
  if (!form) { return; }

  const dataNode = document.getElementById('profileData');
  let profile = {};
  try { profile = JSON.parse(dataNode.textContent || '{}'); } catch (error) { profile = {}; }

  const state = {
    skills: Array.isArray(profile.skills) ? profile.skills.slice() : [],
    education: Array.isArray(profile.education) ? profile.education.map(clone) : [],
    projects: Array.isArray(profile.projects) ? profile.projects.map(clone) : [],
    experience: Array.isArray(profile.experience) ? profile.experience.map(clone) : [],
    certifications: Array.isArray(profile.certifications) ? profile.certifications.map(clone) : [],
    achievements: Array.isArray(profile.achievements) ? profile.achievements.slice() : []
  };
  let dirty = false;

  function clone(item) {
    return Object.assign({}, item);
  }

  const saveState = document.getElementById('saveState');
  const errorsBox = document.getElementById('formErrors');

  function setDirty(value) {
    dirty = value;
    saveState.classList.toggle('is-dirty', value);
    saveState.innerHTML = value
      ? '<span class="dot"></span> Unsaved changes'
      : '<span class="dot"></span> All changes saved';
  }

  /* ---------------- repeaters ---------------- */
  function field(label, key, value, options) {
    const opts = options || {};
    const input = opts.textarea
      ? '<textarea class="textarea" rows="' + (opts.rows || 3) + '" data-field="' + key + '" maxlength="' + (opts.max || 3000) + '" placeholder="' + RI.escapeHtml(opts.placeholder || '') + '">' + RI.escapeHtml(value || '') + '</textarea>'
      : '<input class="input" data-field="' + key + '" maxlength="' + (opts.max || 200) + '" value="' + RI.escapeHtml(value || '') + '" placeholder="' + RI.escapeHtml(opts.placeholder || '') + '">';
    const span = opts.span ? ' span-2' : '';
    return '<div class="field' + span + '"><label>' + label + (opts.required ? ' <span class="req">*</span>' : ' <span class="opt">optional</span>') + '</label>' + input + (opts.hint ? '<p class="field-hint">' + opts.hint + '</p>' : '') + '</div>';
  }

  function entryCard(type, label, index, body) {
    return '<div class="repeat-card" data-entry="' + type + '" data-index="' + index + '">' +
      '<div class="repeat-head"><strong><span class="repeat-index">' + (index + 1) + '</span>' + label + '</strong>' +
      '<div class="repeat-actions"><button type="button" class="link-btn is-danger" data-remove="' + type + '" data-index="' + index + '">Remove</button></div></div>' +
      body + '</div>';
  }

  function renderEducation() {
    const host = document.getElementById('educationList');
    if (!state.education.length) {
      host.innerHTML = '<p class="editor-empty-note">No education entries yet. Add your degree to improve the education alignment.</p>';
      return;
    }
    host.innerHTML = state.education.map(function (item, index) {
      return entryCard('education', 'Education', index,
        '<div class="field-grid">' +
        field('Institution', 'institution', item.institution, { required: true, placeholder: 'Vellore Institute of Technology', max: 160 }) +
        field('Degree', 'degree', item.degree, { placeholder: 'B.Tech', max: 120 }) +
        field('Field of study', 'field', item.field, { placeholder: 'Computer Science and Engineering', max: 120 }) +
        field('Score / CGPA', 'score', item.score, { placeholder: 'CGPA 8.7/10', max: 60 }) +
        field('Start', 'start_date', item.start_date, { placeholder: '2021', max: 40 }) +
        field('End', 'end_date', item.end_date, { placeholder: '2025', max: 40 }) +
        field('Location', 'location', item.location, { placeholder: 'Vellore, India', max: 120, span: true }) +
        '</div>');
    }).join('');
  }

  function renderProjects() {
    const host = document.getElementById('projectList');
    if (!state.projects.length) {
      host.innerHTML = '<p class="editor-empty-note">Projects are the strongest signal for students. Add two or three.</p>';
      return;
    }
    host.innerHTML = state.projects.map(function (item, index) {
      return entryCard('projects', 'Project', index,
        '<div class="field-grid">' +
        field('Project name', 'name', item.name, { required: true, placeholder: 'CampusConnect', max: 160 }) +
        field('Tech stack', 'tech', item.tech, { placeholder: 'React, Node.js, MongoDB', max: 220 }) +
        field('Link', 'link', item.link, { placeholder: 'https://github.com/...', max: 300, span: true }) +
        field('Description (one bullet per line)', 'description', item.description, {
          textarea: true, rows: 4, span: true, max: 3000,
          placeholder: 'Built a MERN app where students form study groups.\nDesigned REST APIs for notes and events.'
        }) +
        '</div>');
    }).join('');
  }

  function renderExperience() {
    const host = document.getElementById('experienceList');
    if (!state.experience.length) {
      host.innerHTML = '<p class="editor-empty-note">No experience yet — internships, freelance work and research all count.</p>';
      return;
    }
    host.innerHTML = state.experience.map(function (item, index) {
      return entryCard('experience', 'Experience', index,
        '<div class="field-grid">' +
        field('Role', 'role', item.role, { required: true, placeholder: 'Backend Developer Intern', max: 160 }) +
        field('Company', 'company', item.company, { placeholder: 'Zeta Innovations', max: 160 }) +
        field('Start', 'start_date', item.start_date, { placeholder: 'May 2024', max: 40 }) +
        field('End', 'end_date', item.end_date, { placeholder: 'Jul 2024', max: 40 }) +
        field('Location', 'location', item.location, { placeholder: 'Bengaluru, India', max: 120, span: true }) +
        field('Description (one bullet per line)', 'description', item.description, {
          textarea: true, rows: 4, span: true, max: 3000,
          placeholder: 'Built three Flask endpoints for an internal reporting tool.\nOptimised a slow SQL report query.'
        }) +
        '</div>');
    }).join('');
  }

  function renderCertifications() {
    const host = document.getElementById('certificationList');
    if (!state.certifications.length) {
      host.innerHTML = '<p class="editor-empty-note">Certifications are optional. Add only ones you completed.</p>';
      return;
    }
    host.innerHTML = state.certifications.map(function (item, index) {
      return entryCard('certifications', 'Certification', index,
        '<div class="field-grid three">' +
        field('Certification name', 'name', item.name, { required: true, placeholder: 'AWS Certified Cloud Practitioner', max: 180 }) +
        field('Issuer', 'issuer', item.issuer, { placeholder: 'Amazon Web Services', max: 160 }) +
        field('Year', 'year', item.year, { placeholder: '2024', max: 20 }) +
        '</div>');
    }).join('');
  }

  function renderAchievements() {
    const host = document.getElementById('achievementList');
    if (!state.achievements.length) {
      host.innerHTML = '<p class="editor-empty-note">Awards, hackathons and contest rankings are worth listing.</p>';
      return;
    }
    host.innerHTML = state.achievements.map(function (text, index) {
      return '<div class="repeat-card" data-entry="achievements" data-index="' + index + '">' +
        '<div class="repeat-head"><strong><span class="repeat-index">' + (index + 1) + '</span>Achievement</strong>' +
        '<div class="repeat-actions"><button type="button" class="link-btn is-danger" data-remove="achievements" data-index="' + index + '">Remove</button></div></div>' +
        '<input class="input" data-field="achievement" maxlength="400" value="' + RI.escapeHtml(text) + '" placeholder="Finalist, Smart India Hackathon 2024">' +
        '</div>';
    }).join('');
  }

  function renderSkills() {
    const host = document.getElementById('skillsTags');
    host.innerHTML = state.skills.map(function (skill, index) {
      return '<span class="tag">' + RI.escapeHtml(skill) +
        '<button type="button" aria-label="Remove ' + RI.escapeHtml(skill) + '" data-remove-skill="' + index + '">×</button></span>';
    }).join('');
    document.getElementById('skillCount').textContent = state.skills.length + (state.skills.length === 1 ? ' skill' : ' skills');
  }

  function renderAll() {
    renderSkills();
    renderEducation();
    renderProjects();
    renderExperience();
    renderCertifications();
    renderAchievements();
  }

  /* ---------------- events ---------------- */
  form.addEventListener('click', function (event) {
    const addBtn = event.target.closest('[data-add]');
    if (addBtn) {
      const type = addBtn.dataset.add;
      if (type === 'education') { state.education.push({}); }
      if (type === 'projects') { state.projects.push({}); }
      if (type === 'experience') { state.experience.push({}); }
      if (type === 'certifications') { state.certifications.push({}); }
      if (type === 'achievements') { state.achievements.push(''); }
      renderAll();
      setDirty(true);
      return;
    }
    const removeBtn = event.target.closest('[data-remove]');
    if (removeBtn) {
      const type = removeBtn.dataset.remove;
      const index = Number(removeBtn.dataset.index);
      if (Number.isNaN(index)) { return; }
      if (type === 'achievements') {
        state.achievements.splice(index, 1);
      } else if (Array.isArray(state[type])) {
        state[type].splice(index, 1);
      }
      renderAll();
      setDirty(true);
      return;
    }
    const skillRemove = event.target.closest('[data-remove-skill]');
    if (skillRemove) {
      state.skills.splice(Number(skillRemove.dataset.removeSkill), 1);
      renderSkills();
      setDirty(true);
    }
  });

  form.addEventListener('input', function (event) {
    const input = event.target.closest('[data-field]');
    if (input) {
      const card = input.closest('[data-entry]');
      if (!card) { return; }
      const type = card.dataset.entry;
      const index = Number(card.dataset.index);
      if (type === 'achievements') {
        state.achievements[index] = input.value;
      } else if (state[type] && state[type][index]) {
        state[type][index][input.dataset.field] = input.value;
      }
      setDirty(true);
      return;
    }
    if (event.target.id === 'summary') {
      document.getElementById('summaryCount').textContent = event.target.value.length;
      setDirty(true);
      return;
    }
    if (event.target.closest('#profileForm') && event.target.matches('input, textarea')) {
      setDirty(true);
    }
  });

  const skillInput = document.getElementById('skillInput');
  function addSkill(raw) {
    const value = String(raw || '').trim().replace(/\s+/g, ' ');
    if (!value) { return; }
    const exists = state.skills.some(function (skill) { return skill.toLowerCase() === value.toLowerCase(); });
    if (!exists && state.skills.length < 80) {
      state.skills.push(value);
      renderSkills();
      setDirty(true);
    }
    skillInput.value = '';
  }
  skillInput.addEventListener('keydown', function (event) {
    if (event.key === 'Enter' || event.key === ',') {
      event.preventDefault();
      addSkill(skillInput.value);
    } else if (event.key === 'Backspace' && !skillInput.value && state.skills.length) {
      state.skills.pop();
      renderSkills();
      setDirty(true);
    }
  });
  skillInput.addEventListener('blur', function () { addSkill(skillInput.value); });
  document.getElementById('skillsInputWrap').addEventListener('click', function (event) {
    if (event.target === event.currentTarget) { skillInput.focus(); }
  });

  document.getElementById('resetProfile').addEventListener('click', function () {
    if (dirty && !window.confirm('Discard all unsaved changes?')) { return; }
    window.location.reload();
  });

  function collectBasics() {
    const get = function (name) {
      const node = form.elements[name];
      return node ? node.value.trim() : '';
    };
    return {
      full_name: get('full_name'),
      headline: get('headline'),
      email: get('email'),
      phone: get('phone'),
      location: get('location'),
      linkedin: get('linkedin'),
      github: get('github'),
      summary: get('summary')
    };
  }

  function showErrors(messages) {
    if (!messages || !messages.length) {
      errorsBox.classList.remove('is-visible');
      errorsBox.innerHTML = '';
      return;
    }
    errorsBox.innerHTML = '<strong>Please fix the following:</strong><ul>' +
      messages.map(function (message) { return '<li>' + RI.escapeHtml(message) + '</li>'; }).join('') + '</ul>';
    errorsBox.classList.add('is-visible');
    errorsBox.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }

  form.addEventListener('submit', async function (event) {
    event.preventDefault();
    const button = document.getElementById('saveProfile');
    showErrors([]);
    const payload = Object.assign(collectBasics(), {
      skills: state.skills,
      education: state.education,
      projects: state.projects,
      experience: state.experience,
      certifications: state.certifications,
      achievements: state.achievements
    });
    RI.setBusy(button, true);
    try {
      const response = await RI.api('/api/profile', { method: 'POST', body: payload });
      setDirty(false);
      RI.toast('Profile saved. Every new resume draft will use it.', 'success', 'Saved to SQLite');
      if (response.completeness !== undefined) {
        const chip = document.querySelector('.topbar-actions .chip');
        if (chip) { chip.textContent = response.completeness + '% complete'; }
      }
    } catch (error) {
      showErrors(error.data && error.data.errors ? error.data.errors : [error.message]);
      RI.toast(error.message, 'error', 'Could not save profile');
    } finally {
      RI.setBusy(button, false);
    }
  });

  window.addEventListener('beforeunload', function (event) {
    if (dirty) {
      event.preventDefault();
      event.returnValue = '';
    }
  });

  if (dataNode && document.getElementById('summary')) {
    document.getElementById('summaryCount').textContent = document.getElementById('summary').value.length;
  }
  renderAll();
  setDirty(false);
})();
