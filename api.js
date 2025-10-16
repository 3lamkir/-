// Пример работы с API
async function loadData() {
    try {
        const response = await fetch('https://jsonplaceholder.typicode.com/users');
        const users = await response.json();
        
        document.getElementById('data').innerHTML = 
            users.map(user => `<p>${user.name} - ${user.email}</p>`).join('');
    } catch (error) {
        console.error('Ошибка:', error);
    }
}

loadData();
