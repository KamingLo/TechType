from controllers import user_controller
from flask import render_template

def init_routes(app):

    # Rute utama
    @app.route('/')
    def index():
        return render_template('index.html')

    # === Rute CRUD User ===
    
    # R: Read (List) & C: Create (Form)
    app.add_url_rule('/users', 'users_page', user_controller.users_page, methods=['GET'])
    
    # C: Create (Action)
    app.add_url_rule('/users/add', 'add_user', user_controller.add_user, methods=['POST'])
    
    # U: Update (Page)
    app.add_url_rule('/users/edit/<int:user_id>', 'edit_user_page', user_controller.edit_user_page, methods=['GET'])
    
    # U: Update (Action)
    app.add_url_rule('/users/update/<int:user_id>', 'update_user_action', user_controller.update_user_action, methods=['POST'])
    
    # D: Delete (Action)
    app.add_url_rule('/users/delete/<int:user_id>', 'delete_user_action', user_controller.delete_user_action, methods=['POST'])