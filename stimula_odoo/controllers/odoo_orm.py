from stimula.service.abstract_orm import AbstractORM


class OdooORM(AbstractORM):
    """Odoo-specific implementation of the AbstractORM class."""

    def __init__(self, env):
        """Initialize with the Odoo environment."""
        self.env = env

    def create(self, table_name: str, values: dict):
        # todo: better way to get model name
        model_name = table_name.replace("_", ".")

        """Create a new record in the specified model."""
        return self.env[model_name].create(values)

    def read(self, model_name: str, record_id: int):
        """Read a record by its ID from the specified model."""
        return self.env[model_name].browse(record_id).read()

    def update(self, model_name: str, record_id: int, values: dict):
        """Update a record by its ID in the specified model."""
        record = self.env[model_name].browse(record_id)
        record.write(values)
        return record

    def delete(self, model_name: str, record_id: int):
        """Delete a record by its ID from the specified model."""
        return self.env[model_name].browse(record_id).unlink()
