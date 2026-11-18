class MarketplaceError(Exception):
    pass


class Forbidden(MarketplaceError):
    pass


class Conflict(MarketplaceError):
    pass


class InvalidInput(MarketplaceError):
    pass


class OrderNotFound(MarketplaceError):
    pass
