/*
 * The APK URL is intentionally configuration-only. Do not put AMD API keys or
 * other server credentials in this file or in any browser-delivered asset.
 * A deployment can set window.SEHAT_SAATHI_APK_URL before this script loads.
 */
const modal = document.querySelector('#download-modal')
const note = document.querySelector('#download-note')
const openButtons = document.querySelectorAll('[data-open-download]')
const closeButtons = document.querySelectorAll('[data-close-download]')
const confirmButton = document.querySelector('#confirm-download')

if ('serviceWorker' in navigator && window.location.protocol !== 'file:') {
  window.addEventListener('load', () => navigator.serviceWorker.register('./sw.js'))
}

function openDownload() {
  modal.hidden = false
  note.textContent = ''
  confirmButton.focus()
}

function closeDownload() {
  modal.hidden = true
}

openButtons.forEach((button) => button.addEventListener('click', openDownload))
closeButtons.forEach((button) => button.addEventListener('click', closeDownload))
modal.addEventListener('click', (event) => {
  if (event.target === modal) closeDownload()
})
document.addEventListener('keydown', (event) => {
  if (event.key === 'Escape' && !modal.hidden) closeDownload()
})

confirmButton.addEventListener('click', () => {
  const apkUrl = window.SEHAT_SAATHI_APK_URL || '/downloads/Sehat-Saathi.apk'
  if (!apkUrl) {
    note.textContent = 'The APK package is not configured for this deployment yet. You can still use the live PWA below.'
    return
  }
  const link = document.createElement('a')
  link.href = apkUrl
  link.download = 'Sehat-Saathi.apk'
  link.rel = 'noopener'
  document.body.appendChild(link)
  link.click()
  link.remove()
  note.textContent = 'Your download should begin shortly.'
})
