document.getElementById('auto-search-btn').addEventListener('click', function() {
    var loadingModal = document.getElementById('loading-modal');
    loadingModal.style.display = 'block';

    fetch('/label_stations/discover/')
        .then(response => response.json())
        .then(data => {
            console.log('Станции найдены:', data);
            loadingModal.style.display = 'none';

            var stationsContainer = document.getElementById('stations-container');

            data.forEach(client => {
                // Проверяем, есть ли уже станция с таким UUID
                if (!isUuidDisplayed(client.uuid)) {
                    var saveButton = '';
                    if (!client.exists) {
                        var saveUrl = `/label_stations/save/`;
                        saveButton = `<button class="buttonSaveStation" data-uuid="${client.uuid}" data-ip="${client.address[0]}" data-hostname="${client.hostname}" data-url="${saveUrl}">Сохранить</button>`;
                    }

                    var stationBox = `
                        <div class="project-box-wrapper">
                            <div class="project-box">
                                <div class="project-box-header">
                                    <span>${new Date().toLocaleDateString()}</span>
                                    <div class="more-wrapper">
                                        <button class="project-btn-more">
                                            <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="feather feather-more-vertical">
                                                <circle cx="12" cy="12" r="1" />
                                                <circle cx="12" cy="5" r="1" />
                                                <circle cx="12" cy="19" r="1" />
                                            </svg>
                                        </button>
                                        <svg xmlns="http://www.w3.org/2000/svg" id="Layer_1" enable-background="new 0 0 500 500" viewBox="0 0 500 500">
                                        <path d="m36 407h428c19.882 0 36-16.118 36-36v-242c0-19.882-16.118-36-36-36h-428c-19.882 0-36 16.118-36 36v242c0 19.882 16.118 36 36 36z" fill="#f00"/>
                                        <g fill="#fff"><path d="m178.066 200.063v99.643h-33.263l-24.911-82.059h-1.465v82.059h-20.222v-99.643h34.143l24.031 82.059h1.465v-82.059z"/>
                                        <path d="m219.974 217.647v23.299h35.461v17.291h-35.461v23.885h44.254v17.584h-64.476v-99.643h64.476v17.584z"/>
                                        <path d="m272.87 200.063h21.247l12.309 82.352h2.198l17.877-82.352h23.445l17.878 82.352h2.197l12.31-82.352h21.247l-19.05 99.643h-30.625l-15.68-75.758-15.679 75.758h-30.626z"/>
                                        </g>
                                        </svg>
                                    </div>
                                </div>
                                <div class="project-box-content-header">
                                    <p class="box-content-header">Имя устройства: ${client.hostname}</p>
                                    <p class="box-content-header">UUID: ${client.uuid}</p>
                                    <p class="box-content-subheader">IP: ${client.address[0]}</p>
                                </div>
                                <div class="box-progress-wrapper">
                                    <p class="box-progress-header">Статус:</p>
                                    <div class="box-progress-bar">
                                        <span class="box-progress" style="width: 100%; background-color: #4067f9"></span>
                                    </div>
                                </div>
                                <div class="project-box-footer">
                                    ${saveButton}
                                </div>
                            </div>
                        </div>`;
                    stationsContainer.insertAdjacentHTML('afterbegin', stationBox);
                }
            });

            document.querySelectorAll('.buttonSaveStation').forEach(button => {
                button.addEventListener('click', function() {
                    var uuid = this.getAttribute('data-uuid');
                    var ip = this.getAttribute('data-ip');
                    var hostname = this.getAttribute('data-hostname');
                    var url = this.getAttribute('data-url');

                    saveStation(uuid, hostname, url);
                });
            });
        })
        .catch(error => {
            console.error('Ошибка при поиске станций:', error);
            loadingModal.style.display = 'none';
        });
});

function saveStation(uuid, hostname, url) {
    fetch(url, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCookie('csrftoken')
        },
        body: JSON.stringify({uuid: uuid, hostname: hostname})
    })
    .then(response => response.json())
    .then(data => {
        if (data.status === 'success') {
            alert('Станция успешно сохранена!');
            loadStations();  // Загружаем обновленный список станций
        } else {
            alert('Ошибка при сохранении станции: ' + data.message);
        }
    })
    .catch(error => {
        console.error('Ошибка при сохранении станции:', error);
    });
}

// Функция для получения CSRF-токена
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
function isUuidDisplayed(uuid) {
    // Находим все элементы с классом "box-content-header"
    var elements = document.querySelectorAll('.box-content-header');

    // Перебираем все найденные элементы
    for (var i = 0; i < elements.length; i++) {
        var elementText = elements[i].textContent.trim(); // Получаем текстовое содержимое элемента

        // Проверяем, содержится ли в тексте UUID
        if (elementText.includes(uuid)) {
            return true; // Если UUID найден, возвращаем true
        }
    }
    return false; // Если UUID не найден ни в одном элементе, возвращаем false
}
document.addEventListener('DOMContentLoaded', function() {

    // Функция для замены анимации
    function replaceAnimation(element, newSrc) {
        const newAnimationElement = document.createElement('dotlottie-player');
        newAnimationElement.setAttribute('src', newSrc);
        newAnimationElement.setAttribute('background', 'transparent');
        newAnimationElement.setAttribute('speed', '1');
        newAnimationElement.setAttribute('style', 'width: 40px; height: 40px;');
        newAnimationElement.setAttribute('loop', '');
        newAnimationElement.setAttribute('autoplay', '');

        element.parentNode.replaceChild(newAnimationElement, element);
    }

    function updateStationStatus() {
        fetch(`/label_stations/check_stations/`)
            .then(response => response.json())
            .then(data => {
                data.forEach(client => {
                    const allUuidElements = document.querySelectorAll('.project-box-content-header p.box-content-header');

                    allUuidElements.forEach(uuidElement => {
                        if (uuidElement.textContent.includes(client.uuid)) {
                            const stationElement = uuidElement.closest('.project-box');
                            const participantsElement = stationElement.querySelector('.participants');
                            const boxcontentsubheaderElement = stationElement.querySelector('.box-content-subheader');
                            if (participantsElement) {
                                const statusElement = participantsElement.querySelector('p');
                                const animationElement = participantsElement.querySelector('dotlottie-player');
                                if (statusElement && animationElement) {
                                    // Обновляем текст статуса
                                    statusElement.textContent = 'Статус подключения: Подключено';
                                    boxcontentsubheaderElement.textContent = `IP: ${client.address[0]}`;
                                    // Меняем класс
                                    participantsElement.classList.remove('status-disconnected', 'status-error');
                                    participantsElement.classList.add('status-connected');
                                    // Заменяем анимацию на онлайн
                                    replaceAnimation(animationElement, 'https://lottie.host/0b3cadf9-38da-439b-a106-a05f19b5d43a/9HHLpSV9fj.json');
                                }
                            }
                        }
                    });
                });

                // Сбрасываем статус для станций, которые не ответили
                document.querySelectorAll('.project-box').forEach(function(boxElement) {
                    const uuidElement = boxElement.querySelector('.project-box-content-header p:nth-child(2)');
                    if (uuidElement) {
                        const uuidText = uuidElement.textContent.trim();
                        const uuid = uuidText.replace('UUID: ', '');
                        if (!data.some(client => client.uuid === uuid)) {
                            const participantsElement = boxElement.querySelector('.participants');
                            if (participantsElement) {
                                const statusElement = participantsElement.querySelector('p');
                                const animationElement = participantsElement.querySelector('dotlottie-player');

                                if (statusElement && animationElement) {
                                    statusElement.textContent = 'Статус подключения: Отключено';
                                    participantsElement.classList.remove('status-connected', 'status-error');
                                    participantsElement.classList.add('status-disconnected');
                                    // Заменяем анимацию на оффлайн
                                    replaceAnimation(animationElement, 'https://lottie.host/de9da52a-54d9-4639-a22e-dbab047b77dc/bJEOrrnABg.json');
                                }
                            }
                        }
                    }
                });
            })
            .catch(error => {
                console.error('Ошибка при проверке статуса станций:', error);
            });
    }

    // Начальная проверка при загрузке страницы
    updateStationStatus();

    // Периодическое обновление статуса каждые 5 минут (300000 мс)
    setInterval(updateStationStatus, 300000);
});

document.addEventListener('DOMContentLoaded', function() {
    // Открытие/закрытие выпадающего меню
    document.querySelectorAll('.project-btn-more').forEach(button => {
        button.addEventListener('click', function(event) {
            event.preventDefault();
            const dropdownMenu = this.nextElementSibling; // Ищем следующий элемент после кнопки
            dropdownMenu.style.display = dropdownMenu.style.display === 'block' ? 'none' : 'block';
        });
    });

    // Закрываем меню, если кликнули вне его
    document.addEventListener('click', function(event) {
        if (!event.target.closest('.more-wrapper')) {
            document.querySelectorAll('.dropdown-menu').forEach(menu => {
                menu.style.display = 'none';
            });
        }
    });

    // Обработчик для кнопки "Изменить"
    document.querySelectorAll('.edit-btn').forEach(button => {
        button.addEventListener('click', function() {
            const stationElement = this.closest('.project-box-wrapper');
            const stationNameElement = stationElement.querySelector('.box-content-header');
            const stationNameInput = stationElement.querySelector('.station-name-input');
            const uuidElement = Array.from(stationElement.querySelectorAll('.box-content-header'))
                .find(el => el.textContent.includes("UUID:"));
            const uuid = uuidElement.textContent.split('UUID: ')[1].trim();

            // Переключаемся в режим редактирования
            stationNameElement.style.display = 'none';
            stationNameInput.style.display = 'inline-block';
            stationNameInput.focus();

            // Когда пользователь завершит ввод и нажмет Enter
            stationNameInput.addEventListener('keypress', function(e) {
                if (e.key === 'Enter') {
                    const newName = stationNameInput.value.trim();

                    fetch('/label_stations/update_name/', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-CSRFToken': getCookie('csrftoken')
                        },
                        body: JSON.stringify({ uuid: uuid, name: newName })
                    })
                    .then(response => response.json())
                    .then(data => {
                        if (data.status === 'success') {
                            // Обновляем отображаемое имя станции
                            stationNameElement.textContent = newName;
                            stationNameInput.style.display = 'none';
                            stationNameElement.style.display = 'inline-block';
                        } else {
                            alert('Ошибка при изменении имени станции: ' + data.message);
                        }
                    })
                    .catch(error => {
                        console.error('Ошибка при изменении имени станции:', error);
                    });
                }
            });
        });
    });

    // Обработчик для кнопки "Удалить"
    document.querySelectorAll('.delete-btn').forEach(button => {
        button.addEventListener('click', function() {
            const stationElement = this.closest('.project-box-wrapper'); // Удаляем весь контейнер станции
            const uuidElement = Array.from(stationElement.querySelectorAll('.box-content-header'))
                .find(el => el.textContent.includes("UUID:"));
            const uuid = uuidElement.textContent.split('UUID: ')[1].trim();

            // Подтверждение удаления
            if (confirm('Вы уверены, что хотите удалить эту станцию?')) {
                fetch('/label_stations/delete/', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': getCookie('csrftoken') // Убедитесь, что CSRF-токен добавлен
                    },
                    body: JSON.stringify({ uuid: uuid })
                })
                .then(response => response.json())
                .then(data => {
                    if (data.status === 'success') {
                        alert('Станция успешно удалена.');
                        // Удаляем контейнер станции из DOM
                        stationElement.remove();
                    } else {
                        alert('Ошибка при удалении станции: ' + data.message);
                    }
                })
                .catch(error => {
                    console.error('Ошибка при удалении станции:', error);
                });
            }
        });
    });
});



