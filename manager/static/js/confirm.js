// Attaches a confirm() guard to any form with data-confirm="message",
// so templates never need an inline onsubmit="" handler -- which a
// strict Content-Security-Policy (script-src 'self', no 'unsafe-inline')
// would silently block, letting the action through with no prompt at all.
document.addEventListener("submit", function (event) {
  var form = event.target;
  if (form.dataset && form.dataset.confirm) {
    if (!window.confirm(form.dataset.confirm)) {
      event.preventDefault();
    }
  }
});
