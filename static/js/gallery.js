/* ResumeIQ — template gallery: live mini previews + apply/default actions. */
(function () {
  'use strict';

  const RI = window.RI;
  const dataNode = document.getElementById('templatePreviewData');
  if (!dataNode) { return; }

  let content = {};
  try { content = JSON.parse(dataNode.textContent || '{}'); } catch (error) { content = {}; }

  RI.$$('[data-template-preview]').forEach(function (host) {
    const template = host.dataset.templatePreview;
    host.innerHTML = RI.renderResume(content, template, {
      sections: RI.SECTION_ORDER.map(function (key) {
        return { section_key: key, label: RI.SECTION_LABELS[key], visible: true };
      })
    });
  });

  RI.$$('[data-use-template]').forEach(function (button) {
    button.addEventListener('click', async function () {
      RI.setBusy(button, true);
      try {
        const data = await RI.api('/api/resumes', {
          method: 'POST',
          body: { template: button.dataset.useTemplate }
        });
        window.location.href = data.redirect;
      } catch (error) {
        RI.setBusy(button, false);
        if (error.data && error.data.needs_profile) {
          RI.toast('Your master profile is empty. Add your details or load the demonstration profile first.', 'error', 'Profile required');
        } else {
          RI.toast(error.message, 'error', 'Could not start a draft');
        }
      }
    });
  });

  RI.$$('[data-default-template]').forEach(function (button) {
    button.addEventListener('click', async function () {
      RI.setBusy(button, true);
      try {
        await RI.api('/api/settings', {
          method: 'POST',
          body: { default_template: button.dataset.defaultTemplate, ai_mode: 'auto' }
        });
        RI.$$('.default-badge').forEach(function (badge) { badge.remove(); });
        const card = button.closest('[data-template-card]');
        if (card) {
          const heading = card.querySelector('h3');
          if (heading) {
            const badge = document.createElement('span');
            badge.className = 'default-badge';
            badge.textContent = 'Default';
            heading.appendChild(badge);
          }
        }
        RI.toast('New drafts will use this template by default.', 'success', 'Default updated');
      } catch (error) {
        RI.toast(error.message, 'error', 'Could not update settings');
      } finally {
        RI.setBusy(button, false);
      }
    });
  });
})();
