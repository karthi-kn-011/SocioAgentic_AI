import { toast } from '../components/toast.js';
import { showButtonSpinner, hideButtonSpinner } from '../components/loader.js';

/**
 * Studio View Manager (AI Content Creation & Multi-Platform Previews)
 */
export function initStudioView() {
  const topicInput = document.getElementById('studio-topic-input');
  const themeSelect = document.getElementById('studio-theme-select');
  const toneSelect = document.getElementById('studio-tone-select');
  const providerSelect = document.getElementById('studio-provider-select');
  const generateBtn = document.getElementById('studio-generate-btn');
  const regenerateBtn = document.getElementById('studio-regenerate-btn');
  const quickPicks = document.querySelectorAll('.prompt-chip');

  // Quick-pick prompts
  quickPicks.forEach(chip => {
    chip.addEventListener('click', () => {
      if (topicInput) {
        topicInput.value = chip.dataset.prompt || chip.textContent;
        toast.show('Sample prompt loaded!', 'info', 1500);
      }
    });
  });

  // Generate button handler
  if (generateBtn) {
    generateBtn.addEventListener('click', async () => {
      const topic = topicInput?.value.trim();
      if (!topic) {
        toast.show('Please enter a topic or campaign idea first.', 'error');
        topicInput?.focus();
        return;
      }

      // Collect selected platforms
      const selectedPlatforms = Array.from(
        document.querySelectorAll('input[name="studio-platform"]:checked')
      ).map(cb => cb.value);

      if (selectedPlatforms.length === 0) {
        toast.show('Please select at least one target platform.', 'error');
        return;
      }

      const theme = themeSelect?.value || 'Thought Leadership';
      const tone = toneSelect?.value || 'Professional & Engaging';
      const provider = providerSelect?.value || 'auto';

      showButtonSpinner(generateBtn, `🧠 Generating with ${provider.toUpperCase()}...`);

      try {
        const response = await fetch('/api/v1/posts/generate', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            topic,
            theme,
            tone,
            provider,
            platforms: selectedPlatforms
          })
        });

        if (!response.ok) {
          const errData = await response.json().catch(() => ({}));
          throw new Error(errData.detail || errData.error || `HTTP ${response.status}`);
        }

        const data = await response.json();
        renderStudioResults(data, selectedPlatforms);
        toast.show(`Generated variants via ${data.provider_used}!`, 'success', 3000);
      } catch (err) {
        console.error('Generation error:', err);
        toast.show(`Generation failed: ${err.message}`, 'error', 4000);
      } finally {
        hideButtonSpinner(generateBtn);
      }
    });
  }

  // Regenerate button handler
  if (regenerateBtn) {
    regenerateBtn.addEventListener('click', async () => {
      const currentPostId = window._currentPostId;
      const topic = topicInput?.value.trim();
      const theme = themeSelect?.value || 'Thought Leadership';
      const tone = toneSelect?.value || 'Professional & Engaging';
      const provider = providerSelect?.value || 'auto';
      const selectedPlatforms = Array.from(
        document.querySelectorAll('input[name="studio-platform"]:checked')
      ).map(cb => cb.value);

      if (!currentPostId && !topic) {
        toast.show('Please generate an initial post first.', 'info');
        return;
      }

      showButtonSpinner(regenerateBtn, '🔄 Varying angle...');

      try {
        const response = await fetch('/api/v1/posts/regenerate', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            topic: topic || 'Social Campaign',
            theme,
            tone,
            provider,
            platforms: selectedPlatforms.length ? selectedPlatforms : ['TWITTER', 'LINKEDIN'],
            regenerate_post_id: currentPostId
          })
        });

        if (!response.ok) {
          const errData = await response.json().catch(() => ({}));
          throw new Error(errData.detail || errData.error || `HTTP ${response.status}`);
        }

        const data = await response.json();
        renderStudioResults(data, selectedPlatforms);
        toast.show(`Regenerated new angle (Version ${data.generation_version}) via ${data.provider_used}!`, 'success', 3000);
      } catch (err) {
        console.error('Regeneration error:', err);
        toast.show(`Regeneration failed: ${err.message}`, 'error', 4000);
      } finally {
        hideButtonSpinner(regenerateBtn);
      }
    });
  }

  // Setup platform preview tabs
  setupPreviewTabs();
}

/**
 * Renders the returned generation payload into the Studio preview panel.
 */
export function renderStudioResults(data, requestedPlatforms) {
  const container = document.getElementById('studio-preview-container');
  if (!container) return;

  container.style.display = 'block';

  window._currentPostId = data.post_id;
  window._currentStudioData = data;
  window._currentStudioVariants = data.variants || {};

  // Provider badge
  const providerBadge = document.getElementById('studio-provider-badge');
  if (providerBadge) {
    providerBadge.textContent = `Provider: ${data.provider_used || 'Groq'}`;
  }

  // Score value
  const scoreVal = document.getElementById('studio-score-val');
  if (scoreVal && data.quality) {
    scoreVal.textContent = data.quality.composite_score;
  }

  // AI Feedback summary
  const feedbackEl = document.getElementById('preview-ai-feedback');
  if (feedbackEl && data.quality) {
    feedbackEl.textContent = data.quality.critique_feedback || 'Quality review passed all platform criteria.';
  }

  // Rubric scores chips
  const rubricEl = document.getElementById('preview-ai-rubric-scores');
  if (rubricEl && data.quality) {
    rubricEl.innerHTML = `
      <span>Grammar: <strong>${data.quality.grammar_score}%</strong></span> •
      <span>Topic Relevance: <strong>${data.quality.topic_relevance_score}%</strong></span> •
      <span>Theme Adherence: <strong>${data.quality.theme_adherence_score}%</strong></span> •
      <span>Naturalness: <strong>${data.quality.naturalness_score}%</strong></span>
    `;
  }

  // Select first available platform
  const platforms = Object.keys(data.variants || {});
  const firstPlatform = platforms[0] || (requestedPlatforms && requestedPlatforms[0]) || 'TWITTER';
  selectPreviewTab(firstPlatform);
}

export function setupPreviewTabs() {
  document.querySelectorAll('.preview-tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const platform = btn.dataset.platform;
      if (platform) selectPreviewTab(platform);
    });
  });
}

export function selectPreviewTab(platform) {
  document.querySelectorAll('.preview-tab-btn').forEach(b => {
    b.classList.toggle('active', b.dataset.platform === platform);
  });

  const variants = window._currentStudioVariants || {};
  const variantObj = variants[platform];

  let content = '';
  let hookType = 'Strategic Insight';

  if (typeof variantObj === 'string') {
    content = variantObj;
  } else if (variantObj && typeof variantObj === 'object') {
    content = variantObj.content || '';
    hookType = variantObj.hook_type || 'Insight';
  } else {
    content = `Draft copy for ${platform} will appear here...`;
  }

  const textEl = document.getElementById('preview-post-text');
  if (textEl) textEl.textContent = content;

  // Update hook badge
  const hookBadge = document.getElementById('preview-ai-hook-type');
  if (hookBadge) {
    hookBadge.textContent = `Hook: ${hookType}`;
  }

  // Update character counter
  const charCountEl = document.getElementById('char-count-num');
  const charBarEl = document.getElementById('char-counter-bar');
  if (charCountEl) {
    const len = content.length;
    charCountEl.textContent = `${len} characters`;
    if (platform === 'TWITTER' && len > 280) {
      charBarEl?.classList.add('warning');
    } else {
      charBarEl?.classList.remove('warning');
    }
  }

  // Update platform author handle
  const handleEl = document.getElementById('preview-platform-handle');
  if (handleEl) {
    const handles = {
      'TWITTER': '@SocialAgentAI • X Post',
      'LINKEDIN': 'SocialAgent AI • LinkedIn Article Share',
      'META_FACEBOOK': 'SocialAgent AI • Facebook Post',
      'META_INSTAGRAM': 'socialagent.ai • Instagram Caption'
    };
    handleEl.textContent = handles[platform] || platform;
  }
}
