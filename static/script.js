document.addEventListener('DOMContentLoaded', function () {
  var modeSwitch = document.querySelector('.mode-switch');

  modeSwitch.addEventListener('click', function () {
    document.documentElement.classList.toggle('dark');
    modeSwitch.classList.toggle('active');
  });

  var listView = document.querySelector('.list-view');
  var gridView = document.querySelector('.grid-view');
  var projectsList = document.querySelector('.project-boxes');

  listView.addEventListener('click', function () {
    gridView.classList.remove('active');
    listView.classList.add('active');
    projectsList.classList.remove('jsGridView');
    projectsList.classList.add('jsListView');
  });

  gridView.addEventListener('click', function () {
    gridView.classList.add('active');
    listView.classList.remove('active');
    projectsList.classList.remove('jsListView');
    projectsList.classList.add('jsGridView');
  });

  document.querySelector('.messages-btn').addEventListener('click', function () {
    document.querySelector('.messages-section').classList.add('show');
  });

  document.querySelector('.messages-close').addEventListener('click', function() {
    document.querySelector('.messages-section').classList.remove('show');
  });
});
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

const pusher = new Pusher('c00f7fd1a53d550c0fc6', {  // Замените на ваш PUSHER_KEY
    cluster: 'eu',          // Замените на ваш PUSHER_CLUSTER
    forceTLS: true
});

const channel = pusher.subscribe('notifications');


channel.bind('new-notification', function(data) {
    console.log('online_stations')
    showOnlineStationToast(data.message);
});


function showOnlineStationToast(message) {
    const toastElement = document.getElementById('toast_online_station');
    if (toastElement) {
        toastElement.querySelector('.toast-body').innerText = message;
        const toast = new bootstrap.Toast(toastElement);
        toast.show();
    }
}