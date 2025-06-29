const addSelectBtn = document.getElementById('add-constructor-field');
const removeSelectBtn = document.getElementById('delete-constructor-field');
const selectContainer = document.getElementById('constructor-container');
const checkStructureBtn = document.getElementById('check_structure');


function handleSelectChange(event) {
    const selectedValue = event.target.value;
    const parentDiv = event.target.closest('.row');


    const rightCol = parentDiv.querySelector('.col-right');


    if (!rightCol) {
        console.error('Правая колонка не найдена');
        return;
    }


    rightCol.innerHTML = '';  // Очистка правой колонки

    if (selectedValue === 'constanta') {

        const div = document.createElement('div');
        div.className = 'mb-3';
        // Добавляем input для константы
        const input1 = document.createElement('input');
        input1.type = 'text';
        input1.className = 'form-control mb-2 dynamic-input';
        input1.label = 'Введите константное значение';
        input1.placeholder = 'Введите константное значение';
        input1.required = true;
        div.appendChild(input1);

        const invalidFeedback = document.createElement('div');
        invalidFeedback.className = 'invalid-feedback';
        invalidFeedback.textContent = 'Пожалуйста, заполните это поле.';
        div.appendChild(invalidFeedback);


        rightCol.appendChild(div);
    } else if (selectedValue === 'weight_netto_pack') {

        const input1 = document.createElement('input');
        input1.type = 'number';
        input1.className = 'form-control mb-2 dynamic-input';
        input1.placeholder = 'Общее количество знаков';

        const input2 = document.createElement('input');
        input2.type = 'number';
        input2.className = 'form-control mb-2 dynamic-input';
        input2.placeholder = 'Количество знаков после запятой';

        rightCol.appendChild(input1);
        rightCol.appendChild(input2);
    } else if (selectedValue === 'weight_brutto_pack') {

        const input1 = document.createElement('input');
        input1.type = 'number';
        input1.className = 'form-control mb-2 dynamic-input';
        input1.placeholder = 'Общее количество знаков';

        const input2 = document.createElement('input');
        input2.type = 'number';
        input2.className = 'form-control mb-2 dynamic-input';
        input2.placeholder = 'Количество знаков после запятой';

        rightCol.appendChild(input1);
        rightCol.appendChild(input2);
    } else if (selectedValue === 'weight_netto_box') {

        const input1 = document.createElement('input');
        input1.type = 'number';
        input1.className = 'form-control mb-2 dynamic-input';
        input1.placeholder = 'Общее количество знаков';

        const input2 = document.createElement('input');
        input2.type = 'number';
        input2.className = 'form-control mb-2 dynamic-input';
        input2.placeholder = 'Количество знаков после запятой';

        rightCol.appendChild(input1);
        rightCol.appendChild(input2);
    } else if (selectedValue === 'weight_brutto_box') {

        const input1 = document.createElement('input');
        input1.type = 'number';
        input1.className = 'form-control mb-2 dynamic-input';
        input1.placeholder = 'Общее количество знаков';

        const input2 = document.createElement('input');
        input2.type = 'number';
        input2.className = 'form-control mb-2 dynamic-input';
        input2.placeholder = 'Количество знаков после запятой';

        rightCol.appendChild(input1);
        rightCol.appendChild(input2);
    } else if (selectedValue === 'weight_netto_pallet') {

        const input1 = document.createElement('input');
        input1.type = 'number';
        input1.className = 'form-control mb-2 dynamic-input';
        input1.placeholder = 'Общее количество знаков';

        const input2 = document.createElement('input');
        input2.type = 'number';
        input2.className = 'form-control mb-2 dynamic-input';
        input2.placeholder = 'Количество знаков после запятой';

        rightCol.appendChild(input1);
        rightCol.appendChild(input2);
    } else if (selectedValue === 'weight_brutto_pallet') {

        const input1 = document.createElement('input');
        input1.type = 'number';
        input1.className = 'form-control mb-2 dynamic-input';
        input1.placeholder = 'Общее количество знаков';

        const input2 = document.createElement('input');
        input2.type = 'number';
        input2.className = 'form-control mb-2 dynamic-input';
        input2.placeholder = 'Количество знаков после запятой';

        rightCol.appendChild(input1);
        rightCol.appendChild(input2);
    } else if (selectedValue === 'weight_brutto_all') {
        const input1 = document.createElement('input');
        input1.type = 'number';
        input1.className = 'form-control mb-2 dynamic-input';
        input1.placeholder = 'Общее количество знаков';

        const input2 = document.createElement('input');
        input2.type = 'number';
        input2.className = 'form-control mb-2 dynamic-input';
        input2.placeholder = 'Количество знаков после запятой';

        rightCol.appendChild(input1);
        rightCol.appendChild(input2);
    } else if (selectedValue === 'production_date') {
        const input1 = document.createElement('input');
        input1.type = 'number';
        input1.className = 'form-control mb-2 dynamic-input';
        input1.placeholder = 'Общее количество знаков';

        const newSelect = document.createElement('select');
        newSelect.className = 'form-select mb-2';


        const options = [

        { value: 'ddMMyy', text: 'ddMMyy' },
        { value: 'ddMMyyyy', text: 'ddMMyyyy' },
        { value: 'yyMMdd', text: 'yyMMdd' },
        { value: 'yyyyMMdd', text: 'yyyyMMdd' },
        { value: 'ddMMyy', text: 'ddMMyy' },
        { value: 'ddMMyy', text: 'ddMMyy' },
        { value: 'ddMMyy', text: 'ddMMyy' },
        { value: 'ddMMyy', text: 'ddMMyy' },
            ]

        const main_option = document.createElement('option');
        main_option.value = 'main_option';
        main_option.textContent = 'Выберите формат даты...';
        main_option.selected = true;
        main_option.disabled = true;
        newSelect.appendChild(main_option);


        options.forEach(option => {
        const opt = document.createElement('option');
        opt.value = option.value;
        opt.textContent = option.text;
        newSelect.appendChild(opt);
    });


        rightCol.appendChild(input1);
        rightCol.appendChild(newSelect);

    } else if (selectedValue === 'exp_date') {
        const input1 = document.createElement('input');
        input1.type = 'number';
        input1.className = 'form-control mb-2 dynamic-input';
        input1.placeholder = 'Общее количество знаков';

        const newSelect = document.createElement('select');
        newSelect.className = 'form-select mb-2';


        const options = [

        { value: 'ddMMyy', text: 'ddMMyy' },
        { value: 'ddMMyyyy', text: 'ddMMyyyy' },
        { value: 'yyMMdd', text: 'yyMMdd' },
        { value: 'yyyyMMdd', text: 'yyyyMMdd' },
        { value: 'ddMMyy', text: 'ddMMyy' },
        { value: 'ddMMyy', text: 'ddMMyy' },
        { value: 'ddMMyy', text: 'ddMMyy' },
        { value: 'ddMMyy', text: 'ddMMyy' },
            ]

        const main_option = document.createElement('option');
        main_option.value = 'main_option';
        main_option.textContent = 'Выберите формат даты...';
        main_option.selected = true;
        main_option.disabled = true;
        newSelect.appendChild(main_option);


        options.forEach(option => {
        const opt = document.createElement('option');
        opt.value = option.value;
        opt.textContent = option.text;
        newSelect.appendChild(opt);
    });


        rightCol.appendChild(input1);
        rightCol.appendChild(newSelect);
    } else if (selectedValue === 'pack_number') {

        const input1 = document.createElement('input');
        input1.type = 'number';
        input1.className = 'form-control mb-2 dynamic-input';
        input1.value = '12';
        input1.disabled = true;



        rightCol.appendChild(input1);

    } else if (selectedValue === 'box_number') {
        const input1 = document.createElement('input');
        input1.type = 'number';
        input1.className = 'form-control mb-2 dynamic-input';
        input1.placeholder = 'Общее количество знаков';
        input1.value = '12';
        input1.disabled = true;


        rightCol.appendChild(input1);
    } else if (selectedValue === 'pallet_number') {

        const input1 = document.createElement('input');
        input1.type = 'number';
        input1.className = 'form-control mb-2 dynamic-input';
        input1.placeholder = 'Общее количество знаков';
        input1.value = '17';
        input1.disabled = true;



        rightCol.appendChild(input1);
    } else if (selectedValue === 'article') {

        const input1 = document.createElement('input');
        input1.type = 'number';
        input1.className = 'form-control mb-2 dynamic-input';
        input1.placeholder = 'Общее количество знаков';


        rightCol.appendChild(input1);

    } else if (selectedValue === 'pack_count') {

        const input1 = document.createElement('input');
        input1.type = 'number';
        input1.className = 'form-control mb-2 dynamic-input';
        input1.placeholder = 'Общее количество знаков';



        rightCol.appendChild(input1);

    } else if (selectedValue === 'box_count') {

        const input1 = document.createElement('input');
        input1.type = 'number';
        input1.className = 'form-control mb-2 dynamic-input';
        input1.placeholder = 'Общее количество знаков';



        rightCol.appendChild(input1);
    } else if (selectedValue === 'batch_number') {

        const input1 = document.createElement('input');
        input1.type = 'number';
        input1.className = 'form-control mb-2 dynamic-input';
        input1.placeholder = 'Общее количество знаков';



        rightCol.appendChild(input1);
    } else if (selectedValue === 'fnc1') {

        const input1 = document.createElement('input');
        input1.type = 'text';
        input1.className = 'form-control mb-2 dynamic-input';
        input1.value = 'FNC1';
        input1.disabled = true;


        rightCol.appendChild(input1);
    } else if (selectedValue === 'ai') {

        const select = document.createElement('select');
        select.className = 'form-select mb-2';

        const options = [
        { value: '00', text: '(00) Глобально-уникальный код грузовых контейнеров (Serial Shipping Container Code (SSCC)) - 18 символов' },
        { value: '01', text: '(01) Глобально-уникальный номер торговых продуктов (Global Trade Item Number (GTIN)) - 14 символов' },
        { value: '02', text: '(02) GTIN содержащихся в грузе торговых продуктов (GTIN of Contained Trade Items) - 14 символов' },
        { value: '10', text: '(10) Номер партии/лота (Batch/Lot Number) - переменная, максимально 20 символов' },
        { value: '11', text: '(11) Дата производства (Production Date) - 6 символов' },
        { value: '13', text: '(13) Дата упаковки (Packaging Date) - 6 символов' },
        { value: '17', text: '(17) Дата истечения срока годности (Expiration Date) - 6 символов' },
        { value: '21', text: '(21) Серийный номер (Serial Number) - переменная, максимально 20 символов' },
        { value: '240', text: '(240) Дополнительный идентификатор продукта (Additional Product Identification) - переменная, максимально 20 символов' },
        { value: '241', text: '(241) Номер партии по данным заказчика (Customer Part Number) - переменная, максимально 30 символов' },
        { value: '242', text: '(242) Номер изготовленного под заказ варианта (Made-to-Order Variation Number) - переменная, максимально 6' },
        { value: '250', text: '(250) Второй серийный номер (Secondary Serial Number) - переменная, максимально 30 символов' },
        { value: '253', text: '(253) Глобально-уникальный идентификатор типа документа (GDTI) - переменная, 13-30 символов' },
        { value: '30', text: '(30) Количество грузовых мест (Count of items) - переменная, максимально 8 символов' },
        { value: '3103', text: '(3103) Вес нетто в килограммах (Product Net Weight in kg) - 6 символов' },
        { value: '401', text: '(401) Глобальный идентификатор номера груза (GINC) (Global Identification Number for Consignment) - переменная, максимально 30' },
        { value: '402', text: '(402) Глобальный идентификационный номер отправления (GSIN) (Global Shipment Identification Number) - 17 символов' },
        { value: '8200', text: '(8200) Extended Packaging URL - переменная, максимально 70' },

            ]

        const main_option = document.createElement('option');
        main_option.value = 'main_option';
        main_option.textContent = 'Выберите Application Identifiers...';
        main_option.selected = true;
        main_option.disabled = true;
        select.appendChild(main_option);


        options.forEach(option => {
        const opt = document.createElement('option');
        opt.value = option.value;
        opt.textContent = option.text;
        select.appendChild(opt);
    });


        rightCol.appendChild(select);

    } else if (selectedValue === 'gs') {

        const input1 = document.createElement('input');
        input1.type = 'text';
        input1.className = 'form-control mb-2 dynamic-input';
        input1.placeholder = 'GS';
        input1.value = 'GS';
        input1.disabled = true



        rightCol.appendChild(input1);
    }

}

// Функция для создания новой строки с select
function createNewSelectRow() {
    const newDiv = document.createElement('div');
    newDiv.className = 'row mb-3';

    const leftCol = document.createElement('div');
    leftCol.className = 'col-6'; // Левая колонка для основного select

    const rightCol = document.createElement('div');
    rightCol.className = 'col-6 col-right'; // Правая колонка для динамически добавляемых элементов

    const newSelect = document.createElement('select');
    newSelect.className = 'form-select mb-2';

    const options = [
        { value: 'constanta', text: 'Константа' },
        { value: 'weight_netto_pack', text: 'Вес нетто упаковки' },
        { value: 'weight_brutto_pack', text: 'Вес брутто упаковки' },
        { value: 'weight_netto_box', text: 'Вес нетто короба' },
        { value: 'weight_brutto_box', text: 'Вес брутто короба' },
        { value: 'weight_netto_pallet', text: 'Вес нетто паллета' },
        { value: 'weight_brutto_pallet', text: 'Вес брутто паллета' },
        { value: 'weight_brutto_all', text: 'Общий вес брутто паллета (с поддоном)' },
        { value: 'production_date', text: 'Дата производства' },
        { value: 'exp_date', text: 'Годен до' },
        { value: 'pack_number', text: 'Номер упаковки' },
        { value: 'box_number', text: 'Номер короба' },
        { value: 'pallet_number', text: 'Номер паллеты' },
        { value: 'article', text: 'Артикул' },
        { value: 'pack_count', text: 'Количество вложений в коробе' },
        { value: 'box_count', text: 'Количество коробов на паллете' },
        { value: 'batch_number', text: 'Номер партии' },
        { value: 'fnc1', text: 'FNC1 (ASCII 232)' },
        { value: 'gs', text: 'Group Separator (ASCII 29)' },
        { value: 'ai', text: 'Идентификатор AI' },
    ];

    options.forEach(option => {
        const opt = document.createElement('option');
        opt.value = option.value;
        opt.textContent = option.text;
        newSelect.appendChild(opt);
    });

    newSelect.addEventListener('change', handleSelectChange);

    leftCol.appendChild(newSelect);
    newDiv.appendChild(leftCol);
    newDiv.appendChild(rightCol);
    selectContainer.appendChild(newDiv);

    // Автоматически вызываем handleSelectChange, чтобы отобразить поля для первого выбора
    handleSelectChange({ target: newSelect });
}

// Добавление нового select
addSelectBtn.addEventListener('click', createNewSelectRow);

// Удаление последнего select
removeSelectBtn.addEventListener('click', function() {
    const rows = selectContainer.querySelectorAll('.row.mb-3');
    if (rows.length > 0) {
        selectContainer.removeChild(rows[rows.length - 1]);
    }
});

function getBarcodeStructure() {
    // Получаем выбранный тип штрихкода из селектора #barcode_type
    const barcodeTypeSelect = document.getElementById('barcode_type');
    const barcodeType = barcodeTypeSelect.value;  // Извлекаем выбранное значение
    const barcodeNameInput = document.getElementById('barcode_name');
    const barcodeName = barcodeNameInput.value;

    if (barcodeType === 'Выберите тип штрихкода...' ) {
        alert('Пожалуйста, выберите тип штрихкода.');
        return;  // Останавливаем выполнение, если тип не выбран
    }

    if (!barcodeName) {
        alert("Не запаолнено поле - Название штрихкода!");
        return;
    }

    const rows = document.querySelectorAll('#constructor-container .row');
    const barcodeStructure = [];
    const weighTypes = [
            'weight_netto_pack',
            'weight_brutto_pack',
            'weight_netto_box',
            'weight_brutto_box',
            'weight_netto_pallet',
            'weight_brutto_pallet',
            'weight_brutto_all'
        ];
    const dateTypes = [
        'production_date',
        'exp_date'
    ];
    const onlyLengthTypes = [
        'pack_number',
        'box_number',
        'pallet_number',
        'article',
        'pack_count',
        'box_count',
        'batch_number',

    ]



    rows.forEach(row => {
        const fieldType = row.querySelector('select'); // Находим select в строке
        const inputs = row.querySelectorAll('input'); // Находим все input в строке
        const selects = row.querySelectorAll('select');



        const field = {
            "field_type": fieldType.value
        };

        if (fieldType.value === 'constanta') {
            field["value"] = inputs[0].value;
            field["length"] = inputs[0].value.length;
        } else if (weighTypes.includes(fieldType.value)) {
            field['length'] = inputs[0].value;
            field['decimalPlaces'] = inputs[1].value;
        } else if (dateTypes.includes(fieldType.value)) {
            field['length'] = inputs[0].value;
            field['dateFormat'] = selects[1].value
        } else if (fieldType.value === 'ai') {
            field["value"] = selects[1].value;
        } else if (onlyLengthTypes.includes(fieldType.value)) {
            field["length"] = inputs[0].value;
        }


        barcodeStructure.push(field);

    });


    const resultStructure = {
        barcode_type: barcodeType,
        barcode_name: barcodeName,
        fields: barcodeStructure
    };

    return resultStructure;
}

checkStructureBtn.addEventListener('click', function() {
    const rows = getBarcodeStructure();
    console.log(rows)
})

const csrftoken = getCookie('csrftoken');

document.getElementById('save_structureBtn').addEventListener('click', function() {
    const formMain = document.getElementById('dynamicFormMain');


     if (formMain.checkValidity()) {
         const structure = getBarcodeStructure();

         if (structure.fields.length > 0) {
             fetch('', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': csrftoken,
                    'X-Action': 'saveStructure',// Убедитесь, что у вас настроен CSRF-токен
                },
                body: JSON.stringify({ barcode_structure: structure })
            })
            .then(response => response.json())
            .then(data => {
                 if (data.success) {
                    alert('Штрихкод успешно сохранён!');
                  } else {
                    alert('Ошибка при отправке данных: ' + data.error);
                  }
            })
            .catch(error => {
                alert(error);
            });
         } else {
             alert('Стурктура не может быть пустой')
         }
    } else {
         // Если форма не валидна, отображаем ошибки
         formMain.classList.add('was-validated');
     }
})

const sendBarcodeToStations = document.getElementById('sendToStations');



sendBarcodeToStations.addEventListener('click', function () {
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
        'X-Action': 'sendToStations',
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

const deleteBarcode = document.getElementById('deleteBarcode');

deleteBarcode.addEventListener('click', function (){
    const csrfToken = getCookie('csrftoken');

    fetch('', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': csrfToken,
        'X-Action': 'deleteBarcode',
      },
      body: JSON.stringify({ id: deleteBarcode.dataset.fieldId })
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
  })


function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            // Проверяем, если cookie начинается с названия токена (name)
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}


