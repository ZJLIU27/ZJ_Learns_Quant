from strategies.st_trading_system.base import BaseSubStrategy


class BetaDuplicate(BaseSubStrategy):
    id = "dup"
    name = "DupB"
    description = "ok"
    tags = []
    min_rows = 1

    def evaluate(self, df):
        return True, {}
