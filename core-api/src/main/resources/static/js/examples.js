document.querySelectorAll('.chip').forEach(function (chip) {
  chip.addEventListener('click', function () {
    var form = chip.closest('form');
    var input = form.querySelector('input[name="question"]');
    input.value = chip.dataset.question;
    if (typeof form.requestSubmit === 'function') {
      form.requestSubmit();
    } else {
      form.submit();
    }
  });
});
