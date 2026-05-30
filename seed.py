from app import app, db, Category, slugify

with app.app_context():
    db.create_all()

    if Category.query.first():
        print('Categories already exist! Delete instance/shoeworld.db first to re-seed.')
        exit()

    categories_data = [
        {'name': 'Sneakers', 'icon': 'fa-shoe-prints'},
        {'name': 'Formal', 'icon': 'fa-briefcase'},
        {'name': 'School', 'icon': 'fa-graduation-cap'},
        {'name': 'Boots', 'icon': 'fa-boot'},
        {'name': 'Sandals', 'icon': 'fa-socks'},
        {'name': 'Slides', 'icon': 'fa-slippers'},
        {'name': 'Heels', 'icon': 'fa-high-heel'},
        {'name': 'Sports', 'icon': 'fa-running'},
        {'name': "Men's Shoes", 'icon': 'fa-male'},
        {'name': "Women's Shoes", 'icon': 'fa-female'},
        {'name': 'Kids Shoes', 'icon': 'fa-child'},
        {'name': 'Luxury', 'icon': 'fa-crown'},
    ]

    for cd in categories_data:
        cat = Category(name=cd['name'], slug=slugify(cd['name']), icon=cd['icon'])
        db.session.add(cat)

    db.session.commit()
    print(f'Seeded {len(categories_data)} categories. Add products via /admin!')
