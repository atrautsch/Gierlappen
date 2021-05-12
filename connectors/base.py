"""Base Connectors.

The idea is that we can define groups of connectors which get called automatically from traverse and tracking.
We should have label and file metric connectors.
"""

class MetricConnector():

    def add_commit(self, global_state, commit):
        pass

    def get_file_metrics(self, global_state, author, alias_name, original_name):
        pass


class LabelConnector():

    def get_labels(self):
        pass

    def get_inducings(self):
        pass
