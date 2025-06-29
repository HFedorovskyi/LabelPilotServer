document.addEventListener('DOMContentLoaded', function () {
    function showSuccessToastRow() {
        const toastElement = document.getElementById('liveToastNomenclature');
        if (toastElement) {
            const toast = new bootstrap.Toast(toastElement); // Инициализируем Toast
            toast.show(); // Отображаем Toast
        }
    }

    const searchInput = document.getElementById('searchInput');
    const accordionItems = document.querySelectorAll('.accordion-item');

    searchInput.addEventListener('input', function () {
            const query = this.value.toLowerCase().trim();
            const regex = new RegExp(`(${query})`, 'gi');

            accordionItems.forEach(function (item) {
                    const button = item.querySelector('.accordion-button');
                    const buttonText = button.textContent.toLowerCase();

                    if (buttonText.includes(query)) {
                        item.classList.remove('hidden');

                        if (query !== '') {
                            // Подсвечиваем совпадения в тексте кнопки
                            const originalText = button.textContent;
                            const highlightedText = originalText.replace(regex, '<span class="highlight">$1</span>');
                            button.innerHTML = highlightedText;
                        } else {
                            // Убираем подсветку, если строка поиска пуста
                            button.innerHTML = button.textContent;
                        }
                    } else {
                        item.classList.add('hidden');
                    }
            });
    });



    // Обработка отправки формы "Новая номенклатура"
    const saveNomenclatureButton = document.getElementById('saveNomenclatureButton');
    if (saveNomenclatureButton) {
        saveNomenclatureButton.addEventListener('click', function () {
            const csrfToken = getCookie('csrftoken');
            const formElements = document.querySelectorAll('#saveNewNomeclature input, #saveNewNomeclature select');
            const formData = {};
            const modalElement = document.getElementById('newNomenclatureModal');
            const modal = bootstrap.Modal.getOrCreateInstance(modalElement);
            const formMain = document.getElementById('saveNewNomeclature');
            let xAction = 'new_nomenclature'
            if (isEditMode){
                xAction = 'edit_nomenclature'
            }

            if (formMain.checkValidity()) {

                formElements.forEach(function (element) {

                        formData[element.id] = element.value;
                    });

                if (isEditMode && editNomenclatureId) {
                        formData['id'] = editNomenclatureId;
                    }

                fetch('', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': csrfToken,
                        'X-Action': xAction,
                    },
                    body: JSON.stringify(formData)
                })
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        if (isEditMode) {
                            window.location.reload();
                        } else {
                            addNomenclatureToDOM(data.nomenclature);
                            isEditMode = false;
                        }
                        modal.hide();
                        document.querySelectorAll('.modal-backdrop').forEach(backdrop => backdrop.remove());
                        formMain.reset();

                        editNomenclatureId = null;
                        modalLabel.titleText = 'Добавление номенклатуры'
                        showSuccessToastRow();
                    } else {
                        alert(data.error);
                    }
                })
                .catch((error) => {
                    alert(error);
                });
            } else {
                formMain.classList.add('was-validated');
            }
        });

    }





   const deleteButtons = document.querySelectorAll('.deleteNomenclatureButton');


    deleteButtons.forEach(function(button) {
        button.addEventListener('click', function(event) {
            // Получаем уникальный идентификатор из data-атрибута
            const nomenclatureId = event.target.getAttribute('data-id');
            deleteNomenclature(nomenclatureId);
        });
    });

    function deleteNomenclature(id) {
        // Пример использования fetch для отправки DELETE запроса
        fetch(``, {
            method: 'DELETE',
            headers: {
                'X-CSRFToken': getCookie('csrftoken'), // Функция для получения CSRF токена
                'Content-Type': 'application/json',
                'X-Action': 'delete_row_nomenclature'
            },
            body: JSON.stringify({ nomenclatureId: id })
        })
        .then(response => {
            if (response.ok) {
                // Успешное удаление, обновляем интерфейс
                alert(`Номенклатура с ID ${id} удалена.`);
                // Например, удаляем элемент из DOM
                removeNomenclatureFromDOM(id)
            } else {
                // Обработка ошибок
                console.error('Ошибка при удалении номенклатуры.');
            }
        })
        .catch(error => {
            console.error('Ошибка:', error);
        });
    }


    function removeNomenclatureFromDOM(id) {
        const item = document.getElementById(`nomenclature-${id}`);
        if (item) {
            item.remove();
        }
    }


    const nomenclatureModal = new bootstrap.Modal(document.getElementById('newNomenclatureModal'));
    const nomenclatureForm = document.getElementById('saveNewNomeclature');
    const modalLabel = document.getElementById('nomenclatureModalLabel');
    const editButtons = document.querySelectorAll('.editNomenclatureButton');

    let isEditMode = false;
    let editNomenclatureId = null;

     editButtons.forEach(function(button) {

        button.addEventListener('click', function(event) {
            // Получаем уникальный идентификатор из data-атрибута
            const id = event.target.getAttribute('data-id');
            const nomenclature = event.target.getAttribute('data-nomenclature')
            isEditMode = true;
            editNomenclatureId = id;
            modalLabel.textContent = 'Редактирование номенклатуры';
            populateForm(nomenclature);
            nomenclatureModal.show();
        });

    });

    function populateForm(nomenclature) {
        let jsonString = nomenclature
          .replace(/'/g, '"')              // заменяем одинарные кавычки на двойные
          .replace(/None/g, 'null');        // заменяем None на null

        // Парсим строку как JSON
        let jsObject = JSON.parse(jsonString);
        const filtredNomenclatureFieldsElement = document.getElementById('filtred-nomenclature-fields');
        let filtredNomenclatureFields = [];

        if (filtredNomenclatureFieldsElement) {
            try {
                filtredNomenclatureFields = JSON.parse(filtredNomenclatureFieldsElement.textContent);
            } catch (error) {
                console.error('Ошибка парсинга filtred_nomenclature_fields:', error);
            }
        } else {
            console.error('Элемент с ID "filtred-nomenclature-fields" не найден.');
        }
        console.log(jsObject)
        nomenclatureForm.querySelector('#name').value = jsObject.name;
        nomenclatureForm.querySelector('#article').value = jsObject.article;
        nomenclatureForm.querySelector('#close_box_counter').value = jsObject.close_box_counter;
        nomenclatureForm.querySelector('#exp_date').value = jsObject.exp_date;
        nomenclatureForm.querySelector('#portion_container_id').value = jsObject.portion_container_id[0].value;
        nomenclatureForm.querySelector('#box_container_id').value = jsObject.box_container_id[0].value;
        nomenclatureForm.querySelector('#templates_pack_label').value = jsObject.templates_pack_label[0].value;
        nomenclatureForm.querySelector('#templates_box_label').value = jsObject.templates_box_label[0].value;

         filtredNomenclatureFields.forEach(function(field) {
            const input = nomenclatureForm.querySelector(`#${field.name}`);
            if (input) {
                input.value = jsObject[field.name];
            }
        });


    }


    const nomenclatureModalEl = document.getElementById('newNomenclatureModal');
    nomenclatureModalEl.addEventListener('hidden.bs.modal', function () {
        isEditMode = false;
        nomenclatureForm.reset();
    });






    function addNomenclatureToDOM(nomenclature) {
        const listContainer = document.getElementById('accordionExample');
        const newItem = document.createElement('div');
        newItem.classList.add('accordion-item');
        newItem.id = `nomenclature-${nomenclature.id}`;
        const filtred_rows = ['name', 'article', 'exp_date', 'close_box_counter',
                          'created', 'edited', 'order', 'id', 'portion_container_id', 'box_container_id', 'templates_pack_label', 'templates_box_label']
        newItem.innerHTML = `
            <h2 class="accordion-header">
                <button class="accordion-button collapsed" type="button" data-bs-toggle="collapse" data-bs-target="#collapseOne-${nomenclature.article}" aria-expanded="false" aria-controls="collapseOne">
                    Артикул: ${nomenclature.article} - ${nomenclature.name}
                </button>
            </h2>
            <div id="collapseOne-${nomenclature.article}" class="accordion-collapse collapse" data-bs-parent="#accordionExample">
                <div class="accordion-body">
                    <div class="row">
                        <div class="col">
                            <p class="is-pulled-left" style="margin-bottom: 10px;"><b>Срок годности:</b> ${nomenclature.exp_date} суток.</p>
                            <p class="is-pulled-left" style="margin-bottom: 10px;"><b>Максимальное к-во вложений в коробе:</b> ${nomenclature.close_box_counter} шт.</p>
                        </div>
                        <div class="col">
                            <p class="is-pulled-right" style="margin-bottom: 10px;"><b>Тип упаковки (вложение):</b> ${nomenclature.portion_container_id}</p>
                            <p class="is-pulled-right" style="margin-bottom: 10px;"><b>Тип упаковки (короб) :</b> ${nomenclature.box_container_id}</p>
                        </div>
                        <div class="col">
                            <p class="is-pulled-right" style="margin-bottom: 10px;"><b>Шаблон единичной этикетки:</b> ${nomenclature.templates_pack_label}</p>
                            <p class="is-pulled-right" style="margin-bottom: 10px;"><b>Шаблон этикетки короба:</b> ${nomenclature.templates_box_label}</p>
                        </div>
                        <div class="col">
                            <p class="is-pulled-right" style="margin-bottom: 10px;"><b>Дата создания:</b> ${nomenclature.created}</p>
                            <p class="is-pulled-right" style="margin-bottom: 10px;"><b>Дата изменения:</b> ${nomenclature.edited}</p>
                        </div>
                    </div>
                    <!-- Ваши дополнительные данные -->
                    <div class="row row-cols-4">
                        ${Object.entries(nomenclature)
                            .filter(([key, value]) => !filtred_rows.includes(key))
                            .map(([key, value]) => `
                                <div class="col">
                                    <p style="margin-bottom: 10px;">
                                        <b>${key}:</b> ${value}
                                    </p>
                                </div>
                            `).join('')
                        }
                    </div>
                    <button type="button" class="btn btn-primary rounded-pill bg-gradient edit-btn" data-id="${nomenclature.id}">Изменить</button>
                    <button type="button" class="btn btn-danger rounded-pill bg-gradient delete-btn" data-id="${nomenclature.id}">Удалить</button>
                </div>
            </div>
        `;
        listContainer.appendChild(newItem);
    }


    const saveNewRowNomenclatureButton = document.getElementById('saveNewRowNomenclatureButton');
        saveNewRowNomenclatureButton.addEventListener('click', function () {
            const form = document.getElementById('saveNewRowNomenclature');
            const formData = new FormData(form);
            const modal = bootstrap.Modal.getInstance(document.getElementById('newNomenclatureRowModal'));
            const csrfToken = getCookie('csrftoken');


            fetch('', {
                method: 'POST',
                headers: {
                    'X-CSRFToken': csrfToken,
                    'X-Action': 'new_row_nomenclature',
                },
                body: formData
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    if (modal) modal.hide();
                    alert('Реквизит сохранён!')
                    window.location.reload();
                } else {
                    displayErrorNewRow(data.error);
                    console.error('Ошибка сохранения:', data.error);
                }
            })
            .catch((error) => {
                console.error('Ошибка:', error);
                displayErrorNewRow('Произошла ошибка при сохранении:', error);
            });
        });

    function displayErrorNewRow(message) {
        const errorContainerNewRow = document.getElementById('errorBoxNewRow');
        if (errorContainerNewRow) {
            errorContainerNewRow.textContent = message;
            errorContainerNewRow.classList.remove('is-hidden');
            errorContainerNewRow.classList.add('is-danger');
        }
    }


    const editRowNomenclatureButton = document.getElementById('editNomenclatureRow');
    const editRowNomenclatureModal = document.getElementById('editNomenclatureRowModal');
    if (editRowNomenclatureButton && editRowNomenclatureModal) {
        editRowNomenclatureButton.addEventListener('click', function () {
            editRowNomenclatureModal.classList.add('is-active');
        });
    }

    const closeEditNewNomenclatureModal = editRowNomenclatureModal ? editRowNomenclatureModal.querySelectorAll('.delete, .modal-background') : [];

    closeEditNewNomenclatureModal.forEach(function (button) {
        button.addEventListener('click', function () {
            editRowNomenclatureModal.classList.remove('is-active');
        });
    });




    const sendNomenclatureToStations = document.getElementById('sendToStations');

    sendNomenclatureToStations.addEventListener('click', function () {
        const selectedStations = [];
        const checkboxes = document.querySelectorAll('input[type="checkbox"]:checked');

        checkboxes.forEach(checkbox => {
          const uuid = checkbox.id.replace('checkbox-', ''); // Извлекаем UUID из ID чекбокса
          selectedStations.push(uuid);
        });

        if (selectedStations.length === 0) {
          alert('Пожалуйста, выберите хотя бы одну станцию для передачи данных.');
          return;
        }

        const csrfToken = getCookie('csrftoken');  // Функция для получения CSRF-токена

        fetch('', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': csrfToken,
            'X-Action': 'sendNomenclatureToStations',
          },
          body: JSON.stringify({ stations: selectedStations })
        })
        .then(response => response.json())
        .then(data => {
          if (data.success) {
            alert('Данные успешно отправлены на выбранные станции.');
          } else {
            alert('Ошибка при отправке данных: ' + data.message);
          }
        })
        .catch(error => {
          console.error('Ошибка:', error);
          alert('Произошла ошибка при отправке данных.');
        });
      });



    document.addEventListener('click', function (event) {
        if (event.target && event.target.matches('#deleteFieldNomenclatures')) {
            event.preventDefault();
            const userConfirmed = confirm("Вы уверенны, что хотите удалить реквизит?");
            const fieldId = event.target.getAttribute('data-field-id');
            const csrfToken = getCookie('csrftoken');

            if (userConfirmed) {
                fetch('', {
                    method: 'DELETE',
                    headers: {
                        'X-CSRFToken': csrfToken,
                        'X-Action': 'delete_field_nomenclature',
                    },
                    body: JSON.stringify({'field_id': fieldId})
                })
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        alert('Реквизит удалён!')
                        window.location.reload();
                    } else {
                        alert("Error: " + data.error);
                    }
                })
                .catch(error => {
                    console.error('Error:', error);
                    alert("An error occurred.");
                });
            }
        }
    });

    function getCookie(name) {
        let cookieValue = null;
        if (document.cookie && document.cookie !== '') {
            const cookies = document.cookie.split(';');
            for (let i = 0; i < cookies.length; i++) {
                const cookie = cookies[i].trim();
                if (cookie.substring(0, name.length + 1) === (name + '=')) {
                    cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                    break;
                }
            }
        }
        return cookieValue;
    }






});
