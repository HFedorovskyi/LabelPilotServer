document.addEventListener("DOMContentLoaded", () => {

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
})


const deleteButtons = document.querySelectorAll('.deleteLabel');
deleteButtons.forEach(function (button){


    button.addEventListener('click', function () {
        const userConfirmed = confirm("Вы уверенны, что хотите удалить шаблон этикетки?");
                const fieldId = this.dataset.fieldId
                const csrfToken = getCookie('csrftoken');

                if (userConfirmed) {
                    fetch('', {
                        method: 'DELETE',
                        headers: {
                            'X-CSRFToken': csrfToken,
                            'X-Action': 'deleteLabel',
                        },
                        body: JSON.stringify({'field_id': fieldId})
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
