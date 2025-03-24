# Гайд
Далее будет максимально простой гайд по деплою ботиков (или чего покруче на наш сервер).
Я верю что в нашей команде когда нибудь появится крутой devops, который докрутит докер, но пока как есть

# Инициализация

Подключаемся как угодно (я использую Termius, гайдик есть в инете), за данными сервака к @ska_19

Далее создаем рабочую директорию, где будем базироваться ваш проект

```
mkdir my_project
cd my_project
```

Создаем виртуальное окружение

```
python3 -m venv myenv
source myenv/bin/activate
```

# Гит

Если вы первый раз на сервере, то нужно добавить свой ssh ключ в гитхаб:
```
ssh-keygen -t ed25519 -C "your_email@example.com" -f ~/.ssh/id_ed25519_your_name
cat ~/.ssh/id_ed25519_your_name.pub
```

Вставьте скопированный ключ в разделе “SSH and GPG keys” настроек вашего аккаунта на GitHub.

Дальше надо немного пошаманить с конфигурациями

```
touch ~/.ssh/config
vim ~/.ssh/config
```

Добавьте следующие настройки:

```
Host github.com-your_name
    HostName github.com
    User git
    IdentityFile ~/.ssh/id_ed25519_your_name
```

Далее добавить ключи в агент

```
eval "$(ssh-agent -s)"
ssh-add ~/.ssh/id_ed25519_your_name
```

Теперь можно клонировать репозиторий))

```
git clone git@github.com-your_name:SNBNclub/my_project.git
```

# Установка зависимостей

```
pip install -r requirements.txt
```

# БД (postgres)

Для начала входим в постгрес

```
sudo -i -u postgres
```
```
psql
```

Создаем пользователя и базу данных

```
CREATE USER my_user WITH PASSWORD 'my_password';
CREATE DATABASE my_db OWNER my_user;
GRANT ALL PRIVILEGES ON DATABASE my_db TO my_user;
```

Далее выходим из постгреса (бд)

``` 
\q
```

Далее выходим из постгреса (пользователя)

```
exit
```

В дальнейшем, что бы зайти в нашу бд, надо:

```
psql -h localhost -U my_user -d my_db
```


# ВАЖНО!
Не забудьте добавить переменные окружения в файл .env

```
DB_HOST=localhost
DB_PORT=5432
DB_NAME=my_db
DB_USER=my_user
DB_PASS=my_password
```

# Запуск проекта
Проекты должны крутится автономно, поэтому используем утилитку supervisorctl

```
vim /etc/supervisor/conf.d/app_name.conf
```

Там надо заполнить следующие поля:

```
[program:app_name]
command=path_to_python_in_your_venv main.py
directory=path_to_your_project (location of main.py)
autostart=true
autorestart=true
stderr_logfile=/var/log/app_name.err.log
stdout_logfile=/var/log/app_name.out.log
```

Далее запускаем

```
sudo supervisorctl reread
sudo supervisorctl update
```

Логи можно почитать тут

```
less /var/log/app_name.err.log
```

и тут

```
less /var/log/app_name.out.log
```

# Апдейт прода
Если пушите апдейт в прод, то надо рестарнтуь приложение

```
sudo supervisorctl restart app_name
```
