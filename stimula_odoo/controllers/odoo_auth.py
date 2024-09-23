"""
    odoo_auth.py

    Copyright (C) 2024 STML.IO

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU Lesser General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
    GNU Lesser General Public License for more details.

    You should have received a copy of the GNU Lesser General Public License
    along with this program. If not, see <https://www.gnu.org/licenses/>.

    Developer: Romke Jonker
    Contact: romke@stml.io
    Description: This class provides an Odoo specific implementation of the Auth class.
"""
from stimula.service.auth import Auth

from odoo.modules.registry import Registry
from odoo.service import security


class OdooAuth(Auth):
    # set the secret key during instantiation
    def __init__(self, secret_key_function, lifetime_function):
        super().__init__(secret_key_function, lifetime_function)

    def _validate_submitted_credentials(self, database, username, password):
        registry = Registry(database)

        wsgienv = {}
        uid = registry['res.users'].authenticate(database, username, password, wsgienv)

        # verify odoo credentials
        security.check(database, uid, password)

        return uid

    def _validate_token_credentials(self, database, uid, password):
        # verify odoo credentials
        security.check(database, uid, password)

        # verify we can connect to the db
        Registry(database).check_signaling()

        # return database, uid for the connection and cursor objects
        return database, uid
