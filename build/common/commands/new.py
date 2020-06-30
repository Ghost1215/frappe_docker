import os
import frappe
import semantic_version

from frappe.commands.site import _new_site
from frappe.installer import update_site_config
from check_connection import get_config, get_site_config, COMMON_SITE_CONFIG_FILE


def get_password(env_var, default=None):
    return os.environ.get(env_var) or _get_password_from_secret(f"{env_var}_FILE") or default


def _get_password_from_secret(env_var):
    """Fetches the secret value from the docker secret file
    usually located inside /run/secrets/
    Arguments:
        env_var {str} -- Name of the environment variable
        containing the path to the secret file.
    Returns:
        [str] -- Secret value
    """
    passwd = None
    secret_file_path = os.environ.get(env_var)
    if secret_file_path:
        with open(secret_file_path) as secret_file:
            passwd = secret_file.read().strip()

    return passwd


def main():
    config = get_config()
    db_type = 'mariadb'
    db_port = config.get('db_port', 3306)
    db_host = config.get('db_host')
    site_name = os.environ.get("SITE_NAME", 'site1.localhost')
    mariadb_root_username = os.environ.get("DB_ROOT_USER", 'root')
    mariadb_root_password = get_password("MYSQL_ROOT_PASSWORD", 'admin')
    postgres_root_password = get_password("POSTGRES_PASSWORD")

    if postgres_root_password:
        db_type = 'postgres'
        db_host = os.environ.get("POSTGRES_HOST")
        db_port = 5432
        if not db_host:
            db_host = config.get('db_host')
            print('Environment variable POSTGRES_HOST not found.')
            print('Using db_host from common_site_config.json')

        sites_path = os.getcwd()
        common_site_config_path = os.path.join(sites_path, COMMON_SITE_CONFIG_FILE)
        update_site_config("root_login", mariadb_root_username, validate = False, site_config_path = common_site_config_path)
        update_site_config("root_password", postgres_root_password, validate = False, site_config_path = common_site_config_path)

    force = True if os.environ.get("FORCE", None) else False
    install_apps = os.environ.get("INSTALL_APPS", None)
    install_apps = install_apps.split(',') if install_apps else []
    frappe.init(site_name, new_site=True)

    if semantic_version.Version(frappe.__version__).major > 11:
        _new_site(
            None,
            site_name,
            mariadb_root_username=mariadb_root_username,
            mariadb_root_password=mariadb_root_password,
            admin_password=get_password("ADMIN_PASSWORD", 'admin'),
            verbose=True,
            install_apps=install_apps,
            source_sql=None,
            force=force,
            db_type=db_type,
            reinstall=False,
            db_host=db_host,
            db_port=db_port,
        )
    else:
        _new_site(
            None,
            site_name,
            mariadb_root_username=mariadb_root_username,
            mariadb_root_password=mariadb_root_password,
            admin_password=get_password("ADMIN_PASSWORD", 'admin'),
            verbose=True,
            install_apps=install_apps,
            source_sql=None,
            force=force,
            reinstall=False,
        )


    if db_type == "mariadb":
        site_config = get_site_config(site_name)

        mysql_command = 'mysql -h{db_host} -u{mariadb_root_username} -p{mariadb_root_password} -e '.format(
            db_host=config.get('db_host'),
            mariadb_root_username=mariadb_root_username,
            mariadb_root_password=mariadb_root_password
        )

        # update User's host to '%' required to connect from any container
        command = mysql_command + "\"UPDATE mysql.user SET Host = '%' where User = '{db_name}'; FLUSH PRIVILEGES;\"".format(
            db_name=site_config.get('db_name')
        )
        os.system(command)

        # Set db password
        command = mysql_command + "\"ALTER USER '{db_name}'@'%' IDENTIFIED BY '{db_password}'; FLUSH PRIVILEGES;\"".format(
            db_name=site_config.get('db_name'),
            db_password=site_config.get('db_password')
        )
        os.system(command)

        # Grant permission to database
        command = mysql_command + "\"GRANT ALL PRIVILEGES ON \`{db_name}\`.* TO '{db_name}'@'%'; FLUSH PRIVILEGES;\"".format(
            db_name=site_config.get('db_name')
        )
        os.system(command)

    if frappe.redis_server:
        frappe.redis_server.connection_pool.disconnect()

    exit(0)


if __name__ == "__main__":
    main()
