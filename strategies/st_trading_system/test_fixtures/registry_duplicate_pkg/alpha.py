from strategies.st_trading_system.base import BaseSubStrategy


class AlphaDuplicate(BaseSubStrategy):
    id = "dup"
    name = "DupA"
    description = "ok"
    tags = []
    min_rows = 1

    def evaluate(self, df):
        return True, {}
