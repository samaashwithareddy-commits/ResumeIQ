/* ResumeIQ — shared UI helpers, toasts, navigation and resume preview rendering. */
(function () {
  'use strict';

  const TEMPLATE_LABELS = {
    classic: 'ATS Classic',
    modern: 'Modern Professional',
    minimal: 'Minimal Technical'
  };
  const SECTION_LABELS = {
    summary: 'Professional Summary',
    skills: 'Skills',
    education: 'Education',
    projects: 'Projects',
    experience: 'Experience',
    certifications: 'Certifications',
    achievements: 'Achievements'
  };
  const SECTION_ORDER = ['summary', 'skills', 'education', 'projects', 'experience', 'certifications', 'achievements'];

  function $(selector, root) {
    return (root || document).querySelector(selector);
  }
  function $$(selector, root) {
    return Array.prototype.slice.call((root || document).querySelectorAll(selector));
  }
  function escapeHtml(value) {
    return String(value === null || value === undefined ? '' : value).replace(/[&<>"']/g, function (ch) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch];
    });
  }
  function debounce(fn, wait) {
    let timer = null;
    const debounced = function () {
      const args = arguments;
      const context = this;
      clearTimeout(timer);
      timer = setTimeout(function () { fn.apply(context, args); }, wait);
    };
    debounced.cancel = function () { clearTimeout(timer); };
    debounced.flush = function () { clearTimeout(timer); fn.apply(null, arguments); };
    return debounced;
  }

  const toastStack = function () { return document.getElementById('toastStack'); };
  function toast(message, type, title) {
    const stack = toastStack();
    if (!stack) { return; }
    const kind = type || 'info';
    const icons = { success: '✓', error: '!', info: 'i' };
    const node = document.createElement('div');
    node.className = 'toast is-' + kind;
    node.innerHTML =
      '<span class="toast-icon">' + (icons[kind] || 'i') + '</span>' +
      '<div>' + (title ? '<strong>' + escapeHtml(title) + '</strong>' : '') +
      escapeHtml(message) + '</div>';
    stack.appendChild(node);
    while (stack.children.length > 4) { stack.removeChild(stack.firstElementChild); }
    const ttl = kind === 'error' ? 7000 : 4600;
    setTimeout(function () {
      node.style.opacity = '0';
      node.style.transform = 'translateY(6px)';
      node.style.transition = 'opacity .2s ease, transform .2s ease';
      setTimeout(function () { node.remove(); }, 220);
    }, ttl);
  }

  async function api(url, options) {
    const opts = Object.assign({ method: 'GET', headers: {} }, options || {});
    if (opts.body && typeof opts.body !== 'string') {
      opts.headers['Content-Type'] = 'application/json';
      opts.body = JSON.stringify(opts.body);
    }
    let response;
    try {
      response = await fetch(url, opts);
    } catch (error) {
      const networkError = new Error('Could not reach the ResumeIQ server. Is app.py still running?');
      networkError.cause = error;
      throw networkError;
    }
    let data = null;
    const text = await response.text();
    if (text) {
      try { data = JSON.parse(text); } catch (error) { data = null; }
    }
    if (!response.ok) {
      const message = (data && data.error) || ('Request failed (HTTP ' + response.status + ').');
      const err = new Error(message);
      err.status = response.status;
      err.data = data || {};
      throw err;
    }
    return data || {};
  }

  function setBusy(button, busy) {
    if (!button) { return; }
    if (busy) {
      button.dataset.originalLabel = button.innerHTML;
      button.classList.add('is-loading');
      button.disabled = true;
    } else {
      button.classList.remove('is-loading');
      button.disabled = false;
      if (button.dataset.originalLabel) {
        button.innerHTML = button.dataset.originalLabel;
        delete button.dataset.originalLabel;
      }
    }
  }

  function initials(name) {
    const parts = String(name || '').trim().split(/\s+/).filter(Boolean);
    if (!parts.length) { return 'RI'; }
    if (parts.length === 1) { return parts[0].slice(0, 2).toUpperCase(); }
    return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
  }

  function stripScheme(url) {
    return String(url || '').replace(/^https?:\/\//i, '').replace(/\/+$/, '');
  }

  function displayName(basics) {
    return (basics && basics.full_name) || 'Your Name';
  }

  function contactItems(basics) {
    const items = [];
    if (!basics) { return items; }
    ['email', 'phone', 'location'].forEach(function (key) {
      if (basics[key]) { items.push(basics[key]); }
    });
    ['linkedin', 'github'].forEach(function (key) {
      if (basics[key]) { items.push(stripScheme(basics[key])); }
    });
    return items;
  }

  function formatRange(start, end) {
    const a = String(start || '').trim();
    const b = String(end || '').trim();
    if (a && b) { return a + ' – ' + b; }
    return a || b;
  }

  function bulletsHtml(bullets) {
    const list = (bullets || []).filter(function (item) { return String(item || '').trim(); });
    if (!list.length) { return ''; }
    return '<ul class="r-bullets">' + list.map(function (bullet) {
      return '<li>' + escapeHtml(bullet) + '</li>';
    }).join('') + '</ul>';
  }

  function sectionShell(label, body) {
    return '<section class="r-section">' +
      '<div class="r-section-head"><h2 class="r-section-title">' + escapeHtml(label) + '</h2></div>' +
      body + '</section>';
  }

  function renderResume(doc, template, options) {
    const d = doc || {};
    const opts = options || {};
    const basics = d.basics || {};
    const sections = Array.isArray(opts.sections) && opts.sections.length ? opts.sections
      : SECTION_ORDER.map(function (key) { return { section_key: key, label: SECTION_LABELS[key], visible: true }; });
    const contacts = contactItems(basics);

    let html = '<div class="resume-paper tpl-' + escapeHtml(template || 'classic') + (opts.mobile ? ' is-mobile' : '') + '">';
    html += '<header class="r-head">';
    html += '<h1 class="r-name">' + escapeHtml(displayName(basics)) + '</h1>';
    if (basics.headline) { html += '<p class="r-headline">' + escapeHtml(basics.headline) + '</p>'; }
    if (contacts.length) {
      html += '<p class="r-contact">' + contacts.map(function (item) {
        return '<span>' + escapeHtml(item) + '</span>';
      }).join('') + '</p>';
    }
    html += '</header>';

    sections.forEach(function (section) {
      if (!section || section.visible === false) { return; }
      const key = section.section_key || '';
      const label = section.label || SECTION_LABELS[key] || 'Section';
      let body = '';

      if (key === 'summary') {
        const text = String(d.summary || '').trim();
        if (!text) { return; }
        body = '<p class="r-summary">' + escapeHtml(text) + '</p>';
      } else if (key === 'skills') {
        const skills = (d.skills || []).filter(function (skill) { return String(skill || '').trim(); });
        if (!skills.length) { return; }
        body = '<div class="r-skills">' + skills.map(function (skill, index) {
          return (index ? '<span class="r-skill-sep">•</span>' : '') + '<span class="r-skill">' + escapeHtml(skill) + '</span>';
        }).join('') + '</div>';
      } else if (key === 'education') {
        const entries = d.education || [];
        if (!entries.length) { return; }
        body = entries.map(function (item) {
          const degree = [item.degree, item.field].filter(Boolean).join(' ');
          const title = degree || item.institution || 'Education';
          const sub = [degree ? item.institution : '', item.score, item.location].filter(Boolean).join(' · ');
          const dates = formatRange(item.start_date, item.end_date);
          return '<div class="r-entry">' +
            '<div class="r-entry-top"><h3 class="r-entry-title">' + escapeHtml(title) + '</h3>' +
            (dates ? '<span class="r-entry-dates">' + escapeHtml(dates) + '</span>' : '') + '</div>' +
            (sub ? '<div class="r-entry-sub">' + escapeHtml(sub) + '</div>' : '') +
            '</div>';
        }).join('');
      } else if (key === 'projects') {
        const entries = d.projects || [];
        if (!entries.length) { return; }
        body = entries.map(function (item) {
          const meta = [item.tech, stripScheme(item.link)].filter(Boolean).join(' · ');
          return '<div class="r-entry">' +
            '<div class="r-entry-top"><h3 class="r-entry-title">' + escapeHtml(item.name || 'Project') + '</h3></div>' +
            (meta ? '<div class="r-entry-sub">' + escapeHtml(meta) + '</div>' : '') +
            bulletsHtml(item.bullets) + '</div>';
        }).join('');
      } else if (key === 'experience') {
        const entries = d.experience || [];
        if (!entries.length) { return; }
        body = entries.map(function (item) {
          const dates = formatRange(item.start_date, item.end_date);
          const sub = [item.company, item.location].filter(Boolean).join(' · ');
          return '<div class="r-entry">' +
            '<div class="r-entry-top"><h3 class="r-entry-title">' + escapeHtml(item.role || 'Role') + '</h3>' +
            (dates ? '<span class="r-entry-dates">' + escapeHtml(dates) + '</span>' : '') + '</div>' +
            (sub ? '<div class="r-entry-sub">' + escapeHtml(sub) + '</div>' : '') +
            bulletsHtml(item.bullets) + '</div>';
        }).join('');
      } else if (key === 'certifications') {
        const entries = d.certifications || [];
        if (!entries.length) { return; }
        body = '<div class="r-certs">' + entries.map(function (item) {
          const tail = [item.issuer, item.year].filter(Boolean).join(', ');
          return '<div>' + escapeHtml(item.name || 'Certification') + (tail ? '<span class="r-entry-sub"> — ' + escapeHtml(tail) + '</span>' : '') + '</div>';
        }).join('') + '</div>';
      } else if (key === 'achievements') {
        const entries = (d.achievements || []).filter(function (item) { return String(item || '').trim(); });
        if (!entries.length) { return; }
        body = bulletsHtml(entries);
      } else if (key.indexOf('custom:') === 0) {
        const id = key.slice(7);
        const custom = (d.custom_sections || []).find(function (item) { return item.id === id; });
        if (!custom) { return; }
        body = bulletsHtml(custom.bullets);
        if (!body) { return; }
      } else {
        return;
      }
      html += sectionShell(label, body);
    });

    html += '</div>';
    return html;
  }

  function defaultSections() {
    return SECTION_ORDER.map(function (key) {
      return { section_key: key, label: SECTION_LABELS[key], visible: true };
    });
  }

  /* Sidebar (mobile) ------------------------------------------------------- */
  function setupSidebar() {
    const menuBtn = document.getElementById('menuBtn');
    const sidebar = document.getElementById('sidebar');
    const scrim = document.getElementById('sidebarScrim');
    if (!menuBtn || !sidebar || !scrim) { return; }
    function close() {
      sidebar.classList.remove('is-open');
      scrim.hidden = true;
      menuBtn.setAttribute('aria-expanded', 'false');
    }
    menuBtn.addEventListener('click', function () {
      const open = !sidebar.classList.contains('is-open');
      sidebar.classList.toggle('is-open', open);
      scrim.hidden = !open;
      menuBtn.setAttribute('aria-expanded', String(open));
    });
    scrim.addEventListener('click', close);
    document.addEventListener('keydown', function (event) {
      if (event.key === 'Escape') { close(); }
    });
    window.addEventListener('resize', function () {
      if (window.innerWidth > 1080) { close(); }
    });
  }

  /* Global quick actions --------------------------------------------------- */
  function setupActions() {
    document.addEventListener('click', async function (event) {
      const trigger = event.target.closest('[data-action]');
      if (!trigger) { return; }
      const action = trigger.dataset.action;
      if (action === 'create-resume') {
        event.preventDefault();
        setBusy(trigger, true);
        try {
          const data = await api('/api/resumes', { method: 'POST', body: {} });
          window.location.href = data.redirect;
        } catch (error) {
          setBusy(trigger, false);
          toast(error.message, 'error', 'Could not create the draft');
        }
      } else if (action === 'load-demo') {
        event.preventDefault();
        if (!window.confirm('Load the fictional demonstration profile? This replaces your current master profile (saved resumes are kept).')) {
          return;
        }
        setBusy(trigger, true);
        try {
          const data = await api('/api/demo/load', { method: 'POST', body: {} });
          window.location.href = data.matcher_url || data.redirect;
        } catch (error) {
          setBusy(trigger, false);
          toast(error.message, 'error', 'Could not load the demo');
        }
      }
    });

    document.addEventListener('submit', function (event) {
      const form = event.target.closest('form[data-confirm]');
      if (form && !window.confirm(form.dataset.confirm)) {
        event.preventDefault();
      }
    });
  }

  function flashMessages() {
    const holder = document.getElementById('serverFlash');
    if (!holder) { return; }
    let messages = [];
    try { messages = JSON.parse(holder.dataset.messages || '[]'); } catch (error) { messages = []; }
    messages.forEach(function (entry, index) {
      const category = entry[0] || 'info';
      const message = entry[1] || '';
      setTimeout(function () {
        toast(message, category === 'error' ? 'error' : category === 'success' ? 'success' : 'info');
      }, index * 150);
    });
  }

  function pathGet(object, path) {
    return String(path).split('.').reduce(function (acc, key) {
      if (acc === null || acc === undefined) { return undefined; }
      return acc[key];
    }, object);
  }
  function pathSet(object, path, value) {
    const keys = String(path).split('.');
    let target = object;
    for (let i = 0; i < keys.length - 1; i += 1) {
      const key = keys[i];
      if (target[key] === undefined || target[key] === null) {
        target[key] = /^\d+$/.test(keys[i + 1]) ? [] : {};
      }
      target = target[key];
    }
    target[keys[keys.length - 1]] = value;
  }

  window.RI = {
    $: $,
    $$: $$,
    escapeHtml: escapeHtml,
    debounce: debounce,
    toast: toast,
    api: api,
    setBusy: setBusy,
    initials: initials,
    stripScheme: stripScheme,
    renderResume: renderResume,
    defaultSections: defaultSections,
    formatRange: formatRange,
    TEMPLATE_LABELS: TEMPLATE_LABELS,
    SECTION_LABELS: SECTION_LABELS,
    SECTION_ORDER: SECTION_ORDER,
    pathGet: pathGet,
    pathSet: pathSet
  };

  document.addEventListener('DOMContentLoaded', function () {
    setupSidebar();
    setupActions();
    flashMessages();
  });
})();
