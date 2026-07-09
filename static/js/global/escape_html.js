/**
 * Escape text before inserting into innerHTML (DOM XSS prevention).
 */
(function (global) {
  function escapeHtml(value) {
    if (value === null || value === undefined) return '';
    return String(value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  global.escapeHtml = escapeHtml;
})(typeof window !== 'undefined' ? window : globalThis);