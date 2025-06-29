class DynamicTextbox extends fabric.Textbox {
    constructor(text, options) {
        super(text, options);
        this.template = text; // Исходный текст с плейсхолдерами
        this.replaceId = options.replaceId || {}; // Данные для замены плейсхолдеров
        console.log(this.replaceId)
        console.log(1)
        this.userText = this.template; // Пользовательский текст, включающий плейсхолдеры

        // Событие для открытия модального окна
        this.on('mousedblclick', this.openModal.bind(this)); // Двойной клик для редактирования текста
    }

    // Открытие модального окна
        openModal() {
            const modal = new bootstrap.Modal(document.getElementById('editTextModal'));
            const modalTextbox = document.getElementById("modalTextbox");
            modalTextbox.value = this.userText; // Загружаем текущий текст с плейсхолдерами в текстовое поле модального окна
            modal.show();

            const saveButton = document.getElementById("saveText");
            saveButton.onclick = () => {
                this.userText = modalTextbox.value; // Обновляем текст с плейсхолдерами
                this.applyText(); // Убедитесь, что вызывается метод applyText
                modal.hide();
            };
        }

    // Применяем текст с замененными плейсхолдерами
        applyText() {
        console.log(2)
            // Используем правильное регулярное выражение для поиска плейсхолдеров
            const processedText = this.userText.replace(/{{\s*([^{}]+)\s*}}/g, (match, key) => {
                console.log(this.replaceId);
                console.log('Заменяем:', key, 'на', this.replaceId[key]); // Проверяем, что заменяется
                return this.replaceId[key] || match; // Заменяем ключ на значение или оставляем плейсхолдер, если замены нет
            });

            this.set({ text: processedText }); // Устанавливаем обновленный текст
            if (this.canvas) {
                this.canvas.requestRenderAll(); // Перерисовываем холст
            }
        }

    toObject() {
        return {
            ...super.toObject(),
            replaceId: this.replaceId,
            template: this.template,
            userText: this.userText, // Сохраняем отредактированный текст с плейсхолдерами
        };
    }
}


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

// Регистрируем новый тип объекта в Fabric.js
fabric.DynamicTextbox = DynamicTextbox;


// Инициализация Fabric.js холста
function cmToPixels(cm, dpi = 203) {
    const inches = cm / 2.54;
    console.log(inches * dpi);
    return inches * dpi;
}

// Инициализация Fabric.js холста
const canvas = new fabric.Canvas('canvas', {
    preserveObjectStacking: true,
    backgroundColor: '#e8e8e8',
    selection: true,
});
canvas.requestRenderAll();

// Переменная для хранения текущего масштаба
let currentZoom = 1;
let panX = 0, panY = 0; // Начальное смещение

// Получение элементов управления
const frameWidthInput = document.getElementById('canvas-width');
const frameHeightInput = document.getElementById('canvas-height');
const setFrameSizeButton = document.getElementById('set-canvas-size');
const zoomRange = document.getElementById('zoom-range');
const zoomValue = document.getElementById('zoom-value');


// Создание рамки
let frame;
function createFrame(widthPx, heightPx) {
    if (frame) {
        canvas.remove(frame);
    }

    frame = new fabric.Rect({
        left: (canvas.getWidth() - widthPx) / 2,
        top: (canvas.getHeight() - heightPx) / 2,
        width: widthPx,
        height: heightPx,
        fill: '#ffffff', // Белый фон внутри рамки
        stroke: '#808080',
        strokeWidth: 0.5,
        selectable: false,
        hasBorders: false,
        hasControls: false,
        preserveObjectStacking: true

    });

    canvas.add(frame);
    centerFrame();
    canvas.requestRenderAll();
}


function centerFrame() {
    if (frame) {
        frame.set({
            left: (canvas.getWidth() - frame.width * currentZoom) / 2 + panX,
            top: (canvas.getHeight() - frame.height * currentZoom) / 2 + panY
        });
        frame.setCoords();
    }
}


function resizeCanvas() {
    const container = document.getElementById('canvas-container');
    if (!container) {
        console.error('Элемент с ID "canvas-container" не найден.');
        return;
    }

    const rect = container.getBoundingClientRect();

    // Установка размеров холста через Fabric.js
    canvas.setWidth(rect.width);
    canvas.setHeight(rect.height);

    // Если вы используете масштабирование или другие трансформации, возможно, потребуется обновить их здесь

    // Центрирование рамки при изменении размеров холста
    if (frame) {
        centerFrame();
    }

    // Повторный рендер холста
    canvas.requestRenderAll();
}

// Вызов функции после полной загрузки DOM и инициализации Fabric.js
document.addEventListener('DOMContentLoaded', () => {
    resizeCanvas();
    window.addEventListener('resize', resizeCanvas);
});

// Вызов функции при загрузке и изменении размеров окна
window.addEventListener('load', () => {
    if (typeof label_data !== 'undefined') {
    } else {

        resizeCanvas(); // Устанавливаем размеры холста при загрузке страницы

    // Создаем начальную рамку с размерами из инпутов
        const initialWidthCm = cmToPixels(parseFloat(document.getElementById('canvas-width').value));
        const initialHeightCm = cmToPixels(parseFloat(document.getElementById('canvas-height').value));
        createFrame(initialWidthCm, initialHeightCm);
    }
    });

window.addEventListener('resize', resizeCanvas);

// Инициализация начальной рамки
function initializeFrame() {
    const widthCm = parseFloat(frameWidthInput.value);
    const heightCm = parseFloat(frameHeightInput.value);
    const widthPx = cmToPixels(widthCm);
    const heightPx = cmToPixels(heightCm);
    createFrame(widthPx, heightPx);
}
initializeFrame();


zoomRange.addEventListener('input', function() {
    const zoom = parseInt(this.value, 10) / 100;
    canvas.setZoom(zoom);
    currentZoom = zoom;
    canvas.setZoom(currentZoom);
    centerFrame(); // Центрируем рамку после изменения зума

    // Устанавливаем размеры контейнера для прокрутки
    const canvasContainer = document.getElementById('canvas-container');
    canvasContainer.scrollLeft = (canvas.width * currentZoom - canvasContainer.clientWidth) / 2;
    canvasContainer.scrollTop = (canvas.height * currentZoom - canvasContainer.clientHeight) / 2;

    canvas.requestRenderAll();
});


canvas.on('mouse:down', function(opt) {
    const evt = opt.e;
    if (evt.altKey === true) { // Используйте Alt + ЛКМ для панорамирования
        this.isDragging = true;
        this.selection = false;
        this.lastPosX = evt.clientX;
        this.lastPosY = evt.clientY;
    }
});

canvas.on('mouse:move', function(opt) {
    if (this.isDragging) {
        const e = opt.e;
        const vpt = this.viewportTransform;
        vpt[4] += e.clientX - this.lastPosX;
        vpt[5] += e.clientY - this.lastPosY;
        this.requestRenderAll();
        this.lastPosX = e.clientX;
        this.lastPosY = e.clientY;
    }
});

canvas.on('mouse:up', function(opt) {
    this.isDragging = false;
    this.selection = true;
});

// Обработчик изменения размеров рамки
setFrameSizeButton.addEventListener('click', () => {
    const widthCm = parseFloat(frameWidthInput.value);
    const heightCm = parseFloat(frameHeightInput.value);
    if (isNaN(widthCm) || isNaN(heightCm) || widthCm <= 0 || heightCm <= 0) {
        alert('Пожалуйста, введите корректные размеры.');
        return;
    }
    const widthPx = cmToPixels(widthCm);
    const heightPx = cmToPixels(heightCm);
    createFrame(widthPx, heightPx);

    // Обновляем масштабирование, чтобы рамка оставалась в центре
    zoomController.setZoom(currentZoom);

    moveFrameToBack();
});


function moveFrameToBack() {
    if (frame) {
        frame.moveTo(0, 0);

    }
}


// Контроллер зума
class ZoomController {
    constructor(canvas, frame) {
        this.canvas = canvas;
        this.frame = frame;
        this.currentZoom = 1;

        this.bindEvents();
    }

    bindEvents() {
        // Масштабирование через ползунок
        zoomRange.addEventListener('input', (e) => {
            const zoomFactor = parseFloat(e.target.value) / 100;
            this.setZoom(zoomFactor);
            zoomValue.textContent = `${e.target.value}%`;
        });

        // Масштабирование колесом мыши
        this.canvas.on('mouse:wheel', (opt) => {
            const delta = opt.e.deltaY;
            let zoom = this.canvas.getZoom();
            zoom *= 0.999 ** delta;
            zoom = Math.max(0.5, Math.min(3, zoom)); // Ограничение зума от 50% до 300%
            this.setZoom(zoom);
            zoomRange.value = zoom * 100;
            zoomValue.textContent = `${Math.round(zoom * 100)}%`;
            opt.e.preventDefault();
            opt.e.stopPropagation();
        });
    }

    setZoom(zoomFactor) {
        // Масштабирование относительно центра рамки
        const frameBounding = this.frame.getBoundingRect();
        const frameCenter = {
            x: frameBounding.left + frameBounding.width / 2,
            y: frameBounding.top + frameBounding.height / 2
        };

        this.canvas.zoomToPoint(frameCenter, zoomFactor);
        this.currentZoom = zoomFactor;
        this.canvas.requestRenderAll();
    }

    getZoom() {
        return this.currentZoom;
    }
}

// Создание экземпляра контроллера зума
const zoomController = new ZoomController(canvas, frame);


const canvasObjects = {};

function getJSON() {

    const objects = canvas.getObjects().filter(obj => obj !== frame).map(obj => {
        const jsonObject = {
            type: obj.type,
            left: obj.left - frame.left,
            top: obj.top - frame.top,
            width: obj.width * obj.scaleX,
            height: obj.height * obj.scaleY,
            fill: obj.fill,
            lineHeight: obj.lineHeight,
            stroke: obj.stroke,
            strokeWidth: obj.strokeWidth,
            fontSize: obj.fontSize,
            fontFamily: obj.fontFamily,
            fontWeight: obj.fontWeight,
            fontStyle: obj.fontStyle,
            text: obj.text,
            textAlign: obj.textAlign,
            pathAlign: obj.pathAlign,
            underline: obj.underline,
            overline: obj.overline,
            linethrough: obj.linethrough,
            direction: obj.direction,
            textBackgroundColor: obj.textBackgroundColor,
            originX: obj.originX,
            originY: obj.originY,
            scaleX: obj.scaleX,
            scaleY: obj.scaleY,
            selectable: obj.selectable,
            hasBorders: obj.hasBorders,
            hasControls: obj.hasControls,
            id: obj.id || `object_${Date.now()}`


        };

        if ('dataType' in obj) {
            jsonObject.dataType = obj.dataType;
        }
        if ('userText' in obj) {
            jsonObject.userText = obj.userText;
        }
        if ('image_type' in obj) {
            jsonObject.image_type = obj.image_type;
        }
        return jsonObject;
    });
    const width_input = document.getElementById('canvas-width')
    const height_input = document.getElementById('canvas-height')


    const canvasJson = {
        size: {
            width: canvas.getWidth(),
            height: canvas.getHeight(),
},
        frame: {
            left: frame.left,
            top: frame.top,
            width: frame.width,
            height: frame.height,
            widthCm: width_input.value,
            heightCm: height_input.value
        },
        objects: objects
    };

    const jsonString = JSON.stringify(canvasJson, null, 2);
    console.log(jsonString);
    return jsonString

    // Здесь можно реализовать скачивание файла или отправку на сервер
}

document.addEventListener('DOMContentLoaded', async function() {
    if (typeof label_data !== 'undefined') {

        const name_label_input = document.getElementById('nameLabel');
        const save_label_button = document.getElementById('saveLabel');
        const update_label_button = document.getElementById('updateLabel');
        const width_input = document.getElementById('canvas-width');
        const height_input = document.getElementById('canvas-height');

        name_label_input.value = name_label;
        name_label_input.dataset.id = id_label;
        save_label_button.classList.add('d-none');
        update_label_button.classList.remove('d-none');

        const frameData = label_data.frame;
        width_input.value = frameData.widthCm;
        height_input.value = frameData.heightCm;
        createFrame(frameData.width, frameData.height);
        frame.set({
            left: frameData.left,
            top: frameData.top,
            width: frameData.width,
            height: frameData.height,
            fill: '#ffffff', // Белый фон внутри рамки
            stroke: '#808080',
            strokeWidth: 0.5,
            selectable: false,
            hasBorders: false,
            hasControls: false,
            preserveObjectStacking: true
        });

        centerFrame();
        moveFrameToBack();

        // Восстановление объектов
        for (const objectData of label_data.objects) {
            let obj;
            if (objectData.type === 'textbox') {
                if (objectData.id !== 'dynamic-textbox') {
                    obj = new fabric.Textbox(objectData.text, {
                        left: objectData.left + frame.left,
                        top: objectData.top + frame.top,
                        width: objectData.width,
                        height: objectData.height,
                        fill: objectData.fill,
                        lineHeight: objectData.lineHeight,
                        stroke: objectData.stroke,
                        strokeWidth: objectData.strokeWidth,
                        fontSize: objectData.fontSize,
                        fontFamily: objectData.fontFamily,
                        fontWeight: objectData.fontWeight,
                        fontStyle: objectData.fontStyle,
                        textAlign: objectData.textAlign,
                        pathAlign: objectData.pathAlign,
                        underline: objectData.underline,
                        overline: objectData.overline,
                        linethrough: objectData.linethrough,
                        direction: objectData.direction,
                        textBackgroundColor: objectData.textBackgroundColor,
                        originX: objectData.originX,
                        originY: objectData.originY,
                        selectable: objectData.selectable,
                        hasBorders: objectData.hasBorders,
                        hasControls: objectData.hasControls,
                        id: objectData.id,
                    });
                    canvasObjects[obj.id] = obj;


                    // Восстановление дополнительных свойств из objectData
                    if ('dataType' in objectData) {
                        obj.dataType = objectData.dataType;
                    }
                    if ('userText' in objectData) {
                        obj.userText = objectData.userText;
                    }
                    if ('image_type' in objectData) {
                        obj.image_type = objectData.image_type;
                    }
                } else if (objectData.id === 'dynamic-textbox') {
                    obj = new fabric.DynamicTextbox(objectData.text, {
                        left: objectData.left + frame.left,
                        top: objectData.top + frame.top,
                        width: objectData.width,
                        height: objectData.height,
                        fill: objectData.fill,
                        lineHeight: objectData.lineHeight,
                        stroke: objectData.stroke,
                        strokeWidth: objectData.strokeWidth,
                        fontSize: objectData.fontSize,
                        fontFamily: objectData.fontFamily,
                        fontWeight: objectData.fontWeight,
                        fontStyle: objectData.fontStyle,
                        textAlign: objectData.textAlign,
                        pathAlign: objectData.pathAlign,
                        underline: objectData.underline,
                        overline: objectData.overline,
                        linethrough: objectData.linethrough,
                        direction: objectData.direction,
                        textBackgroundColor: objectData.textBackgroundColor,
                        originX: objectData.originX,
                        originY: objectData.originY,
                        selectable: objectData.selectable,
                        hasBorders: objectData.hasBorders,
                        hasControls: objectData.hasControls,
                        id: objectData.id,
                        replaceId: dataFromDB
                    });
                    canvasObjects[obj.id] = obj;


                    // Восстановление дополнительных свойств из objectData
                    if ('dataType' in objectData) {
                        obj.dataType = objectData.dataType;
                    }
                    if ('userText' in objectData) {
                        obj.userText = objectData.userText;
                    }
                }
            } else if (objectData.type === 'image') {
                if (objectData.image_type === 'Barcode') {
                    const barcodeSelect = document.getElementById('barcodeSelect');
                    const optionsArray = Array.from(barcodeSelect.options);
                    const selectedIndex = optionsArray.findIndex(option => option.text === objectData.id);
                    barcodeSelect.selectedIndex = selectedIndex;

                    const selectedOption = barcodeSelect.options[barcodeSelect.selectedIndex];
                    const structure = selectedOption.getAttribute('data-structure');
                    const selectedBarcodeName = selectedOption.getAttribute('data-name'); // Определение переменной

                    if (!structure) {
                        alert('Пожалуйста, введите данные для штрихкода.');
                        continue; // Пропустить добавление этого объекта
                    }

                    try {
                        // Ожидание получения base64 изображения
                        const imageBase64 = await generateBarcodeServer(structure);
                        if (imageBase64) {
                            const imageSrc = `data:image/png;base64,${imageBase64}`;
                            console.log(imageSrc)
                            // Ожидание загрузки изображения Fabric.js
                            fabric.Image.fromURL(imageSrc, function (obj) {
                                obj.set({
                                    left: objectData.left + frame.left, // Используем реальные координаты
                                    top: objectData.top + frame.top,
                                    image_type: 'Barcode',
                                    scaleX: objectData.scaleX,
                                    scaleY: objectData.scaleY,
                                    originX: objectData.originX,
                                    originY: objectData.originY,
                                    id: selectedBarcodeName,
                                });
                                canvasObjects[obj.id] = obj;
                                canvas.add(obj);
                                canvas.requestRenderAll()
                            });

                        } else {
                            alert('Не удалось получить изображение штрихкода от сервера.');
                            continue; // Пропустить добавление этого объекта
                        }
                    } catch (error) {
                        console.error('Ошибка при генерации штрихкода:', error);
                        alert('Произошла ошибка при генерации штрихкода.');
                        continue; // Пропустить добавление этого объекта
                    }
                } else {
                    // Обработка других типов изображений, если необходимо
                    console.warn(`Неизвестный тип изображения: ${objectData.image_type}`);
                    continue; // Пропустить добавление этого объекта
                }
            }
            // Добавьте обработку других типов объектов по необходимости
            if (obj) {
                canvas.add(obj);
            }
        }

        canvas.requestRenderAll();




function getAllMethods(obj) {
    let props = [];
    let currentObj = obj;

    do {
        props = props.concat(Object.getOwnPropertyNames(currentObj));
    } while (currentObj = Object.getPrototypeOf(currentObj));

    return props.sort().filter((e, i, arr) => e != arr[i + 1] && typeof obj[e] === 'function');
}

// Получаем все методы объекта frame
const methods = getAllMethods(frame);
console.log(methods);
    }
});



function addElementToFrame(element) {
    if (!frame) return; // Убедимся, что рамка существует

    // Вычисляем координаты рамки
    const frameLeft = frame.left;
    const frameTop = frame.top;

    // Устанавливаем координаты нового элемента так, чтобы он был внутри рамки
    element.left = frameLeft + (frame.width - element.width ) / 2;
    element.top = frameTop + (frame.height - element.height ) / 2;

    canvas.add(element);
    canvas.requestRenderAll();
}

const toolbarButtons = document.getElementById('toolbar-buttons');

// Инициализируем Collapse для кнопок
const toolbarButtonsCollapse = new bootstrap.Collapse(toolbarButtons, {
    toggle: false
});

function showToolbarButtons() {
    toolbarButtonsCollapse.show();
}

function hideToolbarButtons() {
    toolbarButtonsCollapse.hide();
}

// Функция проверки текстового объекта
function isTextObject(obj) {
    return obj && (
        obj.type === 'text' ||
        obj.type === 'i-text' ||
        obj.type === 'textbox'
    );
}

// Обработчики событий
canvas.on('selection:created', function(e) {
    if (e.selected && e.selected.length > 0 && isTextObject(e.selected[0])) {
        showToolbarButtons();
        updateFontSizeInput();
        updateAlignButton();
        updateFontSelect();
    } else {
        hideToolbarButtons();
    }
});

canvas.on('selection:updated', function(e) {
    if (e.selected && e.selected.length > 0 && isTextObject(e.selected[0])) {
        showToolbarButtons();
        updateFontSizeInput();
        updateAlignButton();
        updateFontSelect();
    } else {
        hideToolbarButtons();
    }
});

canvas.on('selection:cleared', function(e) {
    hideToolbarButtons();
});



const fontSizeInput = document.getElementById('fontSize');
const fontSelect = document.getElementById('fontSelect');


function updateFontSizeInput() {
    const activeObject = canvas.getActiveObject();
    if (isTextObject(activeObject)) {
        fontSizeInput.value = activeObject.fontSize;
    } else {
        fontSizeInput.value = '';
    }
}

function updateFontSelect() {
    const activeObject = canvas.getActiveObject();
    if (isTextObject(activeObject)) {
        fontSelect.value = activeObject.fontFamily;
    } else {
        fontSelect.value = '';
    }
}


fontSizeInput.addEventListener('input', function() {
    const activeObject = canvas.getActiveObject();
    if (isTextObject(activeObject)) {
        const newFontSize = parseInt(this.value, 10);
        if (!isNaN(newFontSize) && newFontSize > 0) {
            activeObject.set('fontSize', newFontSize);
            canvas.requestRenderAll();
        }
    }
});

fontSelect.addEventListener('change', function() {
    // Получаем текущий активный объект на холсте
    const activeObject = canvas.getActiveObject();

    // Проверяем, что объект существует и является текстовым
    if (activeObject && activeObject.type === 'textbox') { // или 'text', в зависимости от используемого объекта
        const newFont = fontSelect.value; // Получаем выбранный шрифт из <select>
        activeObject.set('fontFamily', newFont); // Устанавливаем новый шрифт

        // Перерисовываем холст, чтобы изменения отобразились
        canvas.requestRenderAll();
    } else {
        // Опционально: информируем пользователя, что активный объект не является текстовым
        console.warn('Активный объект не является текстовым или отсутствует.');
    }
});

const alignments = [
  { align: 'left', icon: 'bi-text-left' },
  { align: 'center', icon: 'bi-text-center' },
  { align: 'right', icon: 'bi-text-right' },
  { align: 'justify', icon: 'bi-justify' }
];

const alignBtn = document.getElementById('align-btn');
const alignIcon = alignBtn.querySelector('i');

// Функция обновления иконки кнопки в соответствии с текущим выравниванием
function updateAlignButton() {
  const activeObject = canvas.getActiveObject();
  if (isTextObject(activeObject)) {
    const currentAlign = activeObject.textAlign || 'left';
    // Находим объект выравнивания в массиве
    const alignment = alignments.find(a => a.align === currentAlign);
    if (alignment) {
      // Обновляем класс иконки
      alignIcon.className = `bi ${alignment.icon}`;
    }
  } else {
    // Если объект не выбран или не текстовый, устанавливаем иконку по умолчанию
    alignIcon.className = 'bi bi-text-left';
  }
}


alignBtn.addEventListener('click', function() {
  const activeObject = canvas.getActiveObject();
  if (isTextObject(activeObject)) {
    // Получаем текущее выравнивание
    const currentAlign = activeObject.textAlign || 'left';
    // Находим индекс текущего выравнивания в массиве
    let index = alignments.findIndex(a => a.align === currentAlign);
    // Переходим к следующему выравниванию (циклично)
    index = (index + 1) % alignments.length;
    const newAlignment = alignments[index];
    // Устанавливаем новое выравнивание объекта
    activeObject.set('textAlign', newAlignment.align);
    canvas.requestRenderAll();
    // Обновляем иконку кнопки
    alignIcon.className = `bi ${newAlignment.icon}`;
  }
});


const boldBtn = document.getElementById('bold-btn');
const italicBtn = document.getElementById('italic-btn');
const underlineBtn = document.getElementById('underline-btn');


function updateTextStyle(style, value) {
    const activeObject = canvas.getActiveObject();
    if (isTextObject(activeObject)) {
        activeObject.set(style, value);
        canvas.requestRenderAll();
    }
}

boldBtn.addEventListener('click', function() {
    const activeObject = canvas.getActiveObject();
    if (isTextObject(activeObject)) {
        const isBold = activeObject.fontWeight === 'bold';
        updateTextStyle('fontWeight', isBold ? 'normal' : 'bold');
    }
});

italicBtn.addEventListener('click', function() {
    const activeObject = canvas.getActiveObject();
    if (isTextObject(activeObject)) {
        const isItalic = activeObject.fontStyle === 'italic';
        updateTextStyle('fontStyle', isItalic ? 'normal' : 'italic');
    }
});

underlineBtn.addEventListener('click', function() {
    const activeObject = canvas.getActiveObject();
    if (isTextObject(activeObject)) {
        const isUnderline = activeObject.underline === true;
        updateTextStyle('underline', !isUnderline);
    }
});

let textboxNomenclature = null;  // Переменная для хранения текстового объекта с названием
let textboxArticle = null;  // Переменная для хранения текстового объекта с артикулом
let selectedArticle = '99999';  // Переменная для хранения выбранного артикула
let selectedName = 'Тестовое название номенклатуры';  // Переменная для хранения выбранного названия
let dynamicTextboxes = [];
let dateTextbox = null;
let selectedOperator = null
let selectedWeightNettoPack = 99.999
let selectedWeightBruttoPack = 99.999
let selectedWeightNettoBox = 99.999
let selectedWeightBruttoBox = 99.999
let selectedWeightNettoPallet = 99.999
let selectedWeightBruttoPallet = 99.999
let allDataSelectedNomenclature = null
let dateExpTextbox = null



document.getElementById('nomenclatureSelect').addEventListener('change', function() {
  const selectedOption = this.options[this.selectedIndex];
  selectedName = selectedOption.textContent.trim(); // Обновляем selectedName
  allDataSelectedNomenclature = selectedOption.getAttribute('data-all')
  const itemData = JSON.parse(allDataSelectedNomenclature);


  // Если текстовое поле для номенклатуры уже существует, обновляем его текст
  if (canvasObjects['nomenclature']) {
    canvasObjects['nomenclature'].set({ text: selectedName });
    dataFromDB.name = selectedName;
    dataFromDB.article = itemData.article;
    updateNomenclatureForAll(selectedName);
    canvas.requestRenderAll(); // Перерисовываем холст после изменения текста
  }

  // Если текстовое поле для артикула уже существует, обновляем его текст
  if (canvasObjects['article']) {
    canvasObjects['article'].set({ text: itemData.article });
    canvas.requestRenderAll(); // Перерисовываем холст после изменения текста артикула
  }
});

// Обработчик события для кнопки добавления номенклатуры
document.getElementById('addNomenclatureBtn').addEventListener('click', function() {
  if (!selectedName) {
    alert('Пожалуйста, выберите номенклатуру.'); // Если не выбрано значение, показываем предупреждение
    return;
  }

  // Если текстовое поле для номенклатуры еще не существует, создаем его и добавляем на канвас
  if (!textboxNomenclature) {
    textboxNomenclature = new fabric.Textbox(selectedName, {
      left: 100,
      top: 100,
      width: 200,
      fontSize: 16,
      fill: '#000000',
      fontFamily: 'Arial',
      textAlign: 'left',
      id: 'nomenclature',
      selectable: true,
    });


    textboxNomenclature.set
    canvasObjects[textboxNomenclature.id] = textboxNomenclature
    dataFromDB.name = selectedName;
    dataFromDB.article = selectedArticle;
    addElementToFrame(textboxNomenclature);
  }
});

// Обработчик события для кнопки добавления артикула
document.getElementById('addArticleButton').addEventListener('click', function() {
  if (selectedArticle) {
    // Обновление или создание текстового объекта для артикула
    if (textboxArticle) {
      textboxArticle.set({ text: selectedArticle });
    } else {
      textboxArticle = new fabric.Textbox(selectedArticle, {
        left: 100,
        top: 150,  // Располагаем артикул немного ниже названия
        width: 50,
        fontSize: 16,
        fill: '#000000',
        textAlign: 'left',
        id: 'article'
      });
      canvasObjects[textboxArticle.id] = textboxArticle
      addElementToFrame(textboxArticle);
    }

    canvas.requestRenderAll(); // Обновляем холст
  } else {
    alert('Пожалуйста, выберите номенклатуру перед добавлением артикула.');
  }
});


// Обработка нажатия клавиши Delete для удаления активного объекта
document.addEventListener('keydown', function(event) {
  if (event.key === 'Delete' || event.key === 'Del') { // Проверка на нажатие клавиши Delete
    const activeObject = canvas.getActiveObject();
    if (activeObject) {
      canvas.remove(activeObject); // Удаляем активный объект
      canvas.requestRenderAll(); // Обновляем холст

      // Сбрасываем переменные, если объекты были удалены
      if (activeObject === textboxNomenclature) {
        textboxNomenclature = null;
      }
      if (activeObject === textboxArticle) {
        textboxArticle = null;
      }
    }
  }
});
document.getElementById('custom-textbox').addEventListener('click', function(event) {
  const customTextBox = new fabric.Textbox('Введите текст', {
        left: 300,  // Случайное положение по горизонтали
        top: 100,   // Случайное положение по вертикали
        width: 200,                 // Ширина текстового поля
        fontSize: 16,               // Размер шрифта
        fill: '#000000',            // Цвет текста
        textAlign: 'left',
        id: 'customTextbox',
    });
  canvasObjects[customTextBox.id] = customTextBox
  addElementToFrame(customTextBox);

})



const dataFromDB = {


    name: selectedName,
    article: selectedArticle,
    operator: selectedOperator,
    weight_netto_pack: selectedWeightNettoPack,
    weight_brutto_pack: selectedWeightBruttoPack,
    weight_netto_box: selectedWeightNettoBox,
    weight_brutto_box: selectedWeightBruttoBox,
    weight_netto_pallet: selectedWeightNettoPallet,
    weight_brutto_pallet: selectedWeightBruttoPallet,
    pack_number: '000000000010',
    box_number: '000000000009',
    pallet_number: '46210920240000000',
    pack_count: '99',
    box_count: '100',
    batch_number: '9999999999'


};


nomenclatureSelect = document.getElementById('nomenclatureSelect')
const options = nomenclatureSelect.options;
let dataAll;
if (options.length > 0) {
    // Получаем последний элемент <option>
    const lastOption = options[options.length - 1];

    dataAll = lastOption.getAttribute('data-all'); // Или используйте lastOption.dataset.all
    console.log('Значение data-all последнего элемента:', dataAll);

} else {
    dataAll = null
    console.log('В списке нет опций.');
}

const itemData = JSON.parse(dataAll);
const excludedKeys = ['id', 'order', 'name', 'article', 'close_box_counter',
    'portion_container_id', 'box_container_id', 'templates_pack_label', 'templates_box_label',
    'created', 'edited']; // Убедитесь, что типы совпадают с ключами в itemData

    // Итерируемся по всем ключам itemData
    for (const key in itemData) {
        if (itemData.hasOwnProperty(key)) { // Проверяем, что ключ принадлежит самому объекту, а не прототипу
            // Проверяем, находится ли ключ в списке исключений
            if (!excludedKeys.includes(key)) {
                // Добавляем ключ-значение в dataFromDB
                dataFromDB[key] = itemData[key];

                // Дополнительно: можно обновлять или создавать объекты на Canvas
                // В зависимости от вашего случая использования, вы можете добавить логику для этого
                // Например:
            }
        }
    }
console.log(dataFromDB)
// Обработчик клика для добавления комбинированного текстового поля
document.getElementById('dynamic-textbox').addEventListener('click', function() {
    dynamicTextbox = new fabric.DynamicTextbox('Добавьте свой динамический текст...', {
        left: 50,
        top: 50,
        width: 300,
        fontSize: 12,
        fill: '#000000',
        textAlign: 'left',
        id: 'dynamic-textbox',
        replaceId: dataFromDB // Заменяем плейсхолдеры на реальные данные
    });

    dynamicTextbox.scaleX = currentZoom;
    dynamicTextbox.scaleY = currentZoom;

    canvasObjects[dynamicTextbox.id] = dynamicTextbox
    addElementToFrame(dynamicTextbox);
    dynamicTextboxes.push(dynamicTextbox);
    canvas.requestRenderAll();  // Перерисовываем холст, чтобы увидеть добавленный текст
});

function updateNomenclatureForAll(newNomenclature) {
    dynamicTextboxes.forEach((textbox) => {
        textbox.replaceId.nomenclature = newNomenclature; // Обновляем значение номенклатуры
        textbox.applyText(); // Применяем обновленный текст для каждого экземпляра
    });
    canvas.requestRenderAll();  // Перерисовываем холст один раз в конце
}

document.getElementById('addOperatorButton').addEventListener('click', function(event) {
    selectedOperator = 'Оператор 1'

    const OperatorOptions = {

    }
  const operatorTextbox = new fabric.Textbox(selectedOperator, {
        left: 150,  // Случайное положение по горизонтали
        top: 150,   // Случайное положение по вертикали
        width: 150,                 // Ширина текстового поля
        fontSize: 16,               // Размер шрифта
        fill: '#000000',            // Цвет текста
        textAlign: 'left',
        id: 'operator',
    });
  canvasObjects[operatorTextbox.id] = operatorTextbox
  addElementToFrame(operatorTextbox);

})

document.getElementById('addWeightNettoPackBtn').addEventListener('click', function(event) {
  const weightNettoPackTextbox = new fabric.Textbox('99.999', {
        left: 275,  // Случайное положение по горизонтали
        top: 20,   // Случайное положение по вертикали
        width: 50,                 // Ширина текстового поля
        fontSize: 16,               // Размер шрифта
        fill: '#000000',            // Цвет текста
        textAlign: 'left',
        id: 'weight_netto_pack',
    });
    canvasObjects[weightNettoPackTextbox.id] = weightNettoPackTextbox
    addElementToFrame(weightNettoPackTextbox);

})

document.getElementById('addWeightBruttoPackBtn').addEventListener('click', function(event) {
  const weightBruttoPackTextbox = new fabric.Textbox('99.999', {
        left: 200,  // Случайное положение по горизонтали
        top: 250,   // Случайное положение по вертикали
        width: 50,                 // Ширина текстового поля
        fontSize: 16,               // Размер шрифта
        fill: '#000000',            // Цвет текста
        textAlign: 'left',
        id: 'weight_brutto_pack',
    });
  canvasObjects[weightBruttoPackTextbox.id] = weightBruttoPackTextbox
  addElementToFrame(weightBruttoPackTextbox);

})

document.getElementById('addWeightNettoBoxBtn').addEventListener('click', function(event) {
  const weightNettoBoxTextbox = new fabric.Textbox('99.999', {
        left: 200,  // Случайное положение по горизонтали
        top: 250,   // Случайное положение по вертикали
        width: 50,                 // Ширина текстового поля
        fontSize: 16,               // Размер шрифта
        fill: '#000000',            // Цвет текста
        textAlign: 'left',
        id: 'weight_netto_box',
    });
  canvasObjects[weightNettoBoxTextbox.id] = weightNettoBoxTextbox
  addElementToFrame(weightNettoBoxTextbox);

})

document.getElementById('addWeightBruttoBoxBtn').addEventListener('click', function(event) {
  const weightBruttoBoxTextbox = new fabric.Textbox('99.999', {
        left: 200,  // Случайное положение по горизонтали
        top: 250,   // Случайное положение по вертикали
        width: 50,                 // Ширина текстового поля
        fontSize: 16,               // Размер шрифта
        fill: '#000000',            // Цвет текста
        textAlign: 'left',
        id: 'weight_brutto_box',
    });
  canvasObjects[weightBruttoBoxTextbox.id] = weightBruttoBoxTextbox
  addElementToFrame(weightBruttoBoxTextbox);

})

document.getElementById('addWeightNettoPalletBtn').addEventListener('click', function(event) {
  const weightNettoPalletTextbox = new fabric.Textbox('99.999', {
        left: 200,  // Случайное положение по горизонтали
        top: 250,   // Случайное положение по вертикали
        width: 50,                 // Ширина текстового поля
        fontSize: 16,               // Размер шрифта
        fill: '#000000',            // Цвет текста
        textAlign: 'left',
        id: 'weight_netto_pallet',
    });
  canvasObjects[weightNettoPalletTextbox.id] = weightNettoPalletTextbox
  addElementToFrame(weightNettoPalletTextbox);

})

document.getElementById('addWeightBruttoPalletBtn').addEventListener('click', function(event) {
  const weightBruttoPalletTextbox = new fabric.Textbox('99.999', {
        left: 200,  // Случайное положение по горизонтали
        top: 250,   // Случайное положение по вертикали
        width: 50,                 // Ширина текстового поля
        fontSize: 16,               // Размер шрифта
        fill: '#000000',            // Цвет текста
        textAlign: 'left',
        id: 'weight_brutto_pallet',
    });
  canvasObjects[weightBruttoPalletTextbox.id] = weightBruttoPalletTextbox
  addElementToFrame(weightBruttoPalletTextbox);

})

document.getElementById('addBoxNumberBtn').addEventListener('click', function(event) {
  const boxNumberTextbox = new fabric.Textbox('000000000009', {
        left: 200,  // Случайное положение по горизонтали
        top: 250,   // Случайное положение по вертикали
        width: 150,                 // Ширина текстового поля
        fontSize: 16,               // Размер шрифта
        fill: '#000000',            // Цвет текста
        textAlign: 'left',
        id: 'box_number',
    });
  canvasObjects[boxNumberTextbox.id] = boxNumberTextbox
  addElementToFrame(boxNumberTextbox);

})

document.getElementById('addPackNumberBtn').addEventListener('click', function(event) {
  const packNumberTextbox = new fabric.Textbox('000000000010', {
        left: 200,  // Случайное положение по горизонтали
        top: 250,   // Случайное положение по вертикали
        width: 150,                 // Ширина текстового поля
        fontSize: 16,               // Размер шрифта
        fill: '#000000',            // Цвет текста
        textAlign: 'left',
        id: 'pack_number',
    });
  canvasObjects[packNumberTextbox.id] = packNumberTextbox
  addElementToFrame(packNumberTextbox);

})

document.getElementById('addPalletNumberBtn').addEventListener('click', function(event) {
  const palletNumberTextbox = new fabric.Textbox('46210920240000000', {
        left: 200,  // Случайное положение по горизонтали
        top: 250,   // Случайное положение по вертикали
        width: 150,                 // Ширина текстового поля
        fontSize: 16,               // Размер шрифта
        fill: '#000000',            // Цвет текста
        textAlign: 'left',
        id: 'pallet_number',
    });
  canvasObjects[palletNumberTextbox.id] = palletNumberTextbox
  addElementToFrame(palletNumberTextbox);

})

document.getElementById('addPackCountBtn').addEventListener('click', function(event) {
  const packCountTextbox = new fabric.Textbox('99', {
        left: 200,  // Случайное положение по горизонтали
        top: 250,   // Случайное положение по вертикали
        width: 40,                 // Ширина текстового поля
        fontSize: 16,               // Размер шрифта
        fill: '#000000',            // Цвет текста
        textAlign: 'left',
        id: 'pack_count',
    });
  canvasObjects[packCountTextbox.id] = packCountTextbox
  addElementToFrame(packCountTextbox);

})

document.getElementById('addBoxCountBtn').addEventListener('click', function(event) {
  const boxCountTextbox = new fabric.Textbox('100', {
        left: 200,  // Случайное положение по горизонтали
        top: 250,   // Случайное положение по вертикали
        width: 40,                 // Ширина текстового поля
        fontSize: 16,               // Размер шрифта
        fill: '#000000',            // Цвет текста
        textAlign: 'left',
        id: 'box_count',
    });
  canvasObjects[boxCountTextbox.id] = boxCountTextbox
  addElementToFrame(boxCountTextbox);

})

document.getElementById('addBatchNumberBtn').addEventListener('click', function(event) {
  const batchNumberTextbox = new fabric.Textbox('9999999999', {
        left: 200,  // Случайное положение по горизонтали
        top: 250,   // Случайное положение по вертикали
        width: 100,                 // Ширина текстового поля
        fontSize: 16,               // Размер шрифта
        fill: '#000000',            // Цвет текста
        textAlign: 'left',
        id: 'batch_number',
    });
  canvasObjects[batchNumberTextbox.id] = batchNumberTextbox
  addElementToFrame(batchNumberTextbox);

})

document.getElementById('addProductionDateButton').addEventListener('click', function() {
    const selectedFormat = document.getElementById('dateFormatSelect').value; // Получаем выбранный формат даты
    const formattedDate = formatDate(selectedFormat); // Получаем отформатированную дату

    // Если текстовое поле для даты еще не существует, создаем его и добавляем на канвас
    if (!dateTextbox) {
        dateTextbox = new fabric.Textbox(formattedDate, {
            left: 100,
            top: 200,
            width: 200,
            fontSize: 16,
            fill: '#000000',
            textAlign: 'left',
            id: 'production_date',
            dataType: selectedFormat
        });
        canvasObjects[dateTextbox.id] = dateTextbox
        addElementToFrame(dateTextbox);
    } else {
        // Если текстовое поле уже существует, обновляем его текст
        dateTextbox.set({ text: formattedDate });
    }
    canvas.requestRenderAll(); // Перерисовываем холст после добавления или изменения текста
});


const dateFormatSelect = document.getElementById('dateFormatSelect');

dateFormatSelect.addEventListener('change', function () {
    const selectedFormat = dateFormatSelect.value; // Получаем выбранный формат даты

    // Проверяем, существует ли текстовое поле
    if (dateTextbox) {
        // Изменяем значение свойства dataType
        dateTextbox.dataType = selectedFormat;
        // Опционально: можно обновить текстовое поле, если нужно
        dateTextbox.set({ text: formatDate(selectedFormat) });
        // Перерисовываем холст, чтобы применить изменения
        canvas.requestRenderAll();
    }
});

document.getElementById('addExpDateButton').addEventListener('click', function() {
    const selectedFormat = document.getElementById('expDateFormatSelect').value; // Получаем выбранный формат даты
    const formattedDate = formatDate(selectedFormat); // Получаем отформатированную дату

    // Если текстовое поле для даты еще не существует, создаем его и добавляем на канвас
    if (!dateExpTextbox) {
        dateExpTextbox = new fabric.Textbox(formattedDate, {
            left: 100,
            top: 200,
            width: 200,
            fontSize: 16,
            fill: '#000000',
            textAlign: 'left',
            id: 'use_by',
            dataType: selectedFormat
        });
        canvasObjects[dateExpTextbox.id] = dateExpTextbox
        addElementToFrame(dateExpTextbox);
    } else {
        // Если текстовое поле уже существует, обновляем его текст
        dateExpTextbox.set({ text: formattedDate });
    }
    canvas.requestRenderAll(); // Перерисовываем холст после добавления или изменения текста
});

document.getElementById('show-json').addEventListener('click', function() {
    const canvasJson = JSON.stringify(canvas.toObject(['id']), null, 2); // Включаем customId в JSON
    alert(canvasJson);
    json2 = getJSON()
    console.log(json2)// Выводим JSON в всплывающем окне
    console.log('Canvas JSON:', canvasJson); // Также выводим JSON в консоль
});


function changeDiv() {
    // Получаем выбранное значение
    var selectedValue = document.getElementById("floatingSelectTextbox").value;

    // Скрываем все div с классом dynamic-div
    var divs = document.getElementsByClassName("dynamic-div");
    for (var i = 0; i < divs.length; i++) {
        divs[i].style.display = "none";
    }

    // Показываем только выбранный div
    if (selectedValue === "1") {
        document.getElementById("div1").style.display = "block";
    } else if (selectedValue === "2") {
        document.getElementById("div2").style.display = "block";
    } else if (selectedValue === "3") {
        document.getElementById("div3").style.display = "block";
    } else if (selectedValue === "4") {
        document.getElementById("div4").style.display = "block";
    } else if (selectedValue === "5") {
        document.getElementById("div5").style.display = "block";
    } else if (selectedValue === "6") {
        document.getElementById("div6").style.display = "block";
    } else if (selectedValue === "7") {
        document.getElementById("div7").style.display = "block";
    } else if (selectedValue === "9") {
        document.getElementById("div9").style.display = "block";
    } else if (selectedValue === "10") {
        document.getElementById("div10").style.display = "block";
    } else if (selectedValue === "11") {
        document.getElementById("div11").style.display = "block";
    } else if (selectedValue === "12") {
        document.getElementById("div12").style.display = "block";
    } else if (selectedValue === "13") {
        document.getElementById("div13").style.display = "block";
    } else if (selectedValue === "14") {
        document.getElementById("div14").style.display = "block";
    } else if (selectedValue === "15") {
        document.getElementById("div15").style.display = "block";
    } else if (selectedValue === "16") {
        document.getElementById("div16").style.display = "block";
    } else if (selectedValue === "17") {
        document.getElementById("div17").style.display = "block";
    } else if (selectedValue === "18") {
        document.getElementById("div18").style.display = "block";
    } else if (selectedValue === "19") {
        document.getElementById("div19").style.display = "block";
    } else if (selectedValue === "20") {
        document.getElementById("div20").style.display = "block";
    }
}

function formatDate(format) {
    const date = new Date();
    const day = String(date.getDate()).padStart(2, '0');
    const month = String(date.getMonth() + 1).padStart(2, '0'); // Месяц начинается с 0
    const year = date.getFullYear();
    const shortMonthNamesRu = ["янв", "фев", "мар", "апр", "май", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"];
    const monthNamesRu = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября", "ноября", "декабря"];

    switch (format) {
        case 'dd.MM.yyyy':
            return `${day}.${month}.${year}`;
        case 'dd/MM/yyyy':
            return `${day}/${month}/${year}`;
        case 'dd-MM-yyyy':
            return `${day}-${month}-${year}`;
        case 'dd MMM yyyy':
            return `${day} ${shortMonthNamesRu[date.getMonth()]} ${year}`;
        case 'MM.yyyy':
            return `${month}.${year}`;
        case 'yyyy-MM-dd':
            return `${year}-${month}-${day}`;
        default:
            return `${day}.${month}.${year}`; // Формат по умолчанию
    }
}

document.getElementById('dateFormatSelect').addEventListener('change', function() {
    const selectedFormat = this.value; // Получаем выбранный формат даты
    const formattedDate = formatDate(selectedFormat); // Получаем отформатированную дату

    // Если текстовое поле для даты уже существует, обновляем его текст
    if (dateTextbox) {
        dateTextbox.set({ text: formattedDate });
        canvas.requestRenderAll(); // Перерисовываем холст после изменения текста
    }
});



async function generateBarcodeServer(structure) {

    const csrfToken = getCookie('csrftoken');

    try {
        const response = await fetch('', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken,
                'X-Action': 'generateBarcode'
            },
            body: JSON.stringify({
                'structure': structure
            })
        });

        const result = await response.json();

        if (result.error) {
            alert('Ошибка: ' + result.error);
        } else {
            // Возвращаем результат, если всё успешно
            return result.png;
        }
    } catch (error) {
        console.error('Ошибка:', error);
        alert('Произошла ошибка при генерации штрихкода.');
    }
}


async function handleGenerateBarcode() {
    const addBarcodeButton = document.getElementById('addBarcodeButton')
    const spans = addBarcodeButton.querySelectorAll('span');
    addBarcodeButton.disabled = true
    spans.forEach(span => span.classList.remove('d-none'));

    const barcodeSelect = document.getElementById('barcodeSelect');
    const selectedOption = barcodeSelect.options[barcodeSelect.selectedIndex];



    selectedBarcodeStructure = selectedOption.getAttribute('data-structure');
    selectedBarcodeName = selectedOption.getAttribute('data-name');

    if (!selectedBarcodeStructure) {
        alert('Пожалуйста, введите данные для штрихкода.');
        return;
    }

    const imageBase64 = await generateBarcodeServer(selectedBarcodeStructure);
    if (imageBase64) {
        addBarcodeToCanvas(imageBase64);
        spans.forEach(span => span.classList.add('d-none'));
        addBarcodeButton.disabled = false
    }
}

document.getElementById('addBarcodeButton').addEventListener('click', handleGenerateBarcode);

function addBarcodeToCanvas(imageBase64) {
    const imageSrc = `data:image/png;base64,${imageBase64}`;
    console.log(imageSrc)
    console.log(21212112)

    fabric.Image.fromURL(imageSrc, function(img) {
        img.set({
            left: 100,
            top: 100,
            scaleX: 1,
            scaleY: 1,
            image_type: 'Barcode',
            angle: 0,
            padding: 0,
            originX: "center",
            originY: "center",
            id: selectedBarcodeName,
        });
        canvasObjects[img.id] = img
        addElementToFrame(img);

    });
}



document.getElementById('saveLabel').addEventListener('click', function() {

    var nameLabel = document.getElementById('nameLabel').value;
    if (nameLabel.trim() === '') {
        alert('Поле "Название метки" не может быть пустым.');
        return;


    } else {

        const csrfToken = getCookie('csrftoken');
        const canvasJson = getJSON()



        fetch('', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken,
                'X-Action': 'saveLabel',
            },
            body: JSON.stringify({
                'structure': canvasJson,
                'name': nameLabel})
        })
        .then(response => response.json())
        .then(data => {
          if (data.success) {
            alert('Шаблон успешно сохранён');
          } else {
            alert('Ошибка при отправке данных: ' + data.message);
          }
        })
        .catch(error => {
          console.error('Ошибка:', error);
          alert('Произошла ошибка при отправке данных.');
        });
}


});