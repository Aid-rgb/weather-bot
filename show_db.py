import shelve

print("=" * 50)
print("СОДЕРЖИМОЕ БАЗЫ ДАННЫХ ИЗБРАННОГО")
print("=" * 50)

with shelve.open("favorites") as db:
    if len(db) == 0:
        print("\nБаза данных пуста. Добавьте город в избранное через бота.")
    else:
        print(f"\nВсего пользователей: {len(db)}\n")
        for user_id, cities in db.items():
            print(f"User ID: {user_id}")
            print(f"Избранные города: {', '.join(cities)}")
            print(f"Количество избранных: {len(cities)}")
            print("-" * 50)
