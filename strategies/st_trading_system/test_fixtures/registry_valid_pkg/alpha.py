from strategies.st_trading_system.base import BaseSubStrategy


class Alpha(BaseSubStrategy):
    id = "alpha"
    name = "Alpha"
    description = "ok"
    tags = []
    min_rows = 1

    def evaluate(self, df):
        return True, {}
