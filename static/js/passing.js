// Одиночный выбор. Штатно radio не снять, поэтому повторный клик снимает отметку.
// Свой ответ - отдельный вариант «Свой вариант»: ввод текста выбирает его, а выбор
// другого варианта текст не стирает - отправится только то, что отмечено.
(() => {
  const form = document.querySelector("form.question");
  if (!form) return;

  const radios = [...form.querySelectorAll("input[type=radio][name=option]")];
  if (!radios.length) return;
  const customRadio = form.querySelector("input[type=radio][name=option][value=custom]");
  const customText = form.querySelector("textarea.choice__custom");

  // Состояние до клика: к моменту события click браузер уже отметил radio.
  const remember = () => radios.forEach((r) => (r.dataset.wasChecked = r.checked ? "1" : ""));
  remember();

  radios.forEach((radio) => {
    radio.addEventListener("click", () => {
      if (radio.dataset.wasChecked) radio.checked = false;
      remember();
    });
  });

  customText?.addEventListener("focus", () => {
    customRadio.checked = true;
    remember();
  });
})();
