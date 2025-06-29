document.addEventListener("DOMContentLoaded", () => {

    let isEditMode = false;
    let editPackId = null;

    document.getElementById('savePackButton').addEventListener('click', function() {
        const formMain = document.getElementById('saveNewPack');
        const formElements = document.querySelectorAll('#saveNewPack input');
        const formData = {};
        const modalElement = document.getElementById('newPack');
        const modal = bootstrap.Modal.getOrCreateInstance(modalElement);
        const csrftoken = getCookie('csrftoken')
        let xAction = 'savePack'

        if (isEditMode){
                xAction = 'edit_pack'
            }

         if (formMain.checkValidity()) {



             formElements.forEach(function (element) {
                        formData[element.name] = element.value;
                    });

             if (isEditMode && editPackId) {
                        formData['id'] = editPackId;
                    }


             fetch('', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': csrftoken,
                        'X-Action': xAction,// Убедитесь, что у вас настроен CSRF-токен
                    },
                    body: JSON.stringify({ pack: formData })
                })
                .then(response => response.json())
                .then(data => {
                     if (data.success) {
                        alert('Упаковка успешно сохранена!');
                        window.location.reload();
                      } else {
                        alert('Ошибка при отправке данных: ' + data.error);
                      }
                })
                .catch(error => {
                    alert(error);
                });
         } else {
             formMain.classList.add('was-validated');
         }
    })

    const deleteButton = document.querySelectorAll('.deletePack')
    deleteButton.forEach(function (button){
        button.addEventListener('click', function () {
        const userConfirmed = confirm("Вы уверенны, что хотите удалить упаковку?");

                const fieldId = this.dataset.fieldId;
                const csrfToken = getCookie('csrftoken');

                if (userConfirmed) {
                    fetch('', {
                        method: 'DELETE',
                        headers: {
                            'X-CSRFToken': csrfToken,
                            'X-Action': 'deletePack',
                        },
                        body: JSON.stringify({'id': fieldId})
                    })
                    .then(response => response.json())
                    .then(data => {
                        if (data.success) {
                            showSuccessToastRow();
                        } else {
                            alert("Error: " + data.error);
                        }
                    })
                    .catch(error => {
                        console.error('Error:', error);
                        alert("An error occurred.");
                    });
                }
    })
    })

    const nomenclatureModal = new bootstrap.Modal(document.getElementById('newPack'));
    const nomenclatureForm = document.getElementById('saveNewPack');
    const modalLabel = document.getElementById('packModalLabel');
    const editPack = document.querySelectorAll('.editPack')



    editPack.forEach(function (button){
        button.addEventListener('click', function (event){
            const id = event.target.getAttribute('data-id');
            const nomenclature = event.target.getAttribute('data-pack')

        })
    })

    function showSuccessToastRow() {
    const toastElement = document.getElementById('liveToastDeletePack');
    if (toastElement) {
        const toast = new bootstrap.Toast(toastElement); // Инициализируем Toast
        toast.show(); // Отображаем Toast
    }
}

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
})