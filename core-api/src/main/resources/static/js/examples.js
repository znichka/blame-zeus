document.querySelectorAll('.chip').forEach(function (chip) {
  chip.addEventListener('click', function () {
    var input = document.querySelector('input[name="question"]');
    var form = input.closest('form');
    input.value = chip.dataset.question;
    if (typeof form.requestSubmit === 'function') {
      form.requestSubmit();
    } else {
      form.submit();
    }
  });
});
