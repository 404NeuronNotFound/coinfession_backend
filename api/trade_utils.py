"""
Utility functions for trade P&L calculations and validations.
"""


def calculate_pnl(trade):
    """
    Calculate realized P&L and ROI for a trade.
    
    Returns:
        dict with keys: realized_pnl, roi
        or None if trade is open or missing required fields
    """
    # Check if trade is open
    if trade.is_open:
        return None
    
    position_type = trade.position_type
    
    # SPOT trades
    if position_type == 'spot':
        if trade.buy_price is None or trade.sell_price is None:
            return None
        
        realized_pnl = (trade.sell_price - trade.buy_price) * trade.quantity - trade.fee
        cost_basis = trade.buy_price * trade.quantity
        roi = (realized_pnl / cost_basis * 100) if cost_basis > 0 else 0.0
        
        return {
            'realized_pnl': round(realized_pnl, 2),
            'roi': round(roi, 2)
        }
    
    # LONG trades
    elif position_type == 'long':
        if (trade.entry_price is None or trade.exit_price is None or 
            trade.collateral is None or trade.leverage is None or trade.quantity is None):
            return None
        
        price_change = trade.exit_price - trade.entry_price
        gross_pnl = price_change * trade.quantity
        realized_pnl = gross_pnl - trade.fee - trade.funding_fees
        
        # Guard against division by zero
        if trade.collateral == 0:
            roi = 0.0
        else:
            roi = (realized_pnl / trade.collateral) * 100
        
        return {
            'realized_pnl': round(realized_pnl, 2),
            'roi': round(roi, 2)
        }
    
    # SHORT trades
    elif position_type == 'short':
        if (trade.entry_price is None or trade.exit_price is None or 
            trade.collateral is None or trade.leverage is None or trade.quantity is None):
            return None
        
        price_change = trade.entry_price - trade.exit_price  # Inverted for short
        gross_pnl = price_change * trade.quantity
        realized_pnl = gross_pnl - trade.fee - trade.funding_fees
        
        # Guard against division by zero
        if trade.collateral == 0:
            roi = 0.0
        else:
            roi = (realized_pnl / trade.collateral) * 100
        
        return {
            'realized_pnl': round(realized_pnl, 2),
            'roi': round(roi, 2)
        }
    
    return None


def calculate_liquidation_price(entry_price, leverage, position_type):
    """
    Calculate liquidation price for a leveraged position.
    
    Args:
        entry_price: Entry price of the position
        leverage: Leverage multiplier (e.g., 5.0 for 5x)
        position_type: 'long' or 'short'
    
    Returns:
        Liquidation price as float, or None if invalid inputs
    """
    if entry_price is None or leverage is None or leverage <= 0:
        return None
    
    if position_type == 'long':
        # Long: liquidation_price = entry_price × (1 - 1/leverage)
        liquidation_price = entry_price * (1 - (1 / leverage))
    elif position_type == 'short':
        # Short: liquidation_price = entry_price × (1 + 1/leverage)
        liquidation_price = entry_price * (1 + (1 / leverage))
    else:
        # Spot has no liquidation
        return None
    
    return round(liquidation_price, 2)


def calculate_quantity_from_collateral(collateral, leverage, entry_price):
    """
    Calculate quantity for long/short positions from collateral.
    
    Args:
        collateral: Amount user invested
        leverage: Leverage multiplier
        entry_price: Entry price
    
    Returns:
        Quantity as float
    """
    if collateral is None or leverage is None or entry_price is None or entry_price == 0:
        return 0.0
    
    position_size = collateral * leverage
    quantity = position_size / entry_price
    
    return quantity


def calculate_unrealized_pnl(trade, current_price):
    """
    Calculate unrealized P&L for an open position.
    
    Args:
        trade: Trade object (must be open)
        current_price: Current market price
    
    Returns:
        dict with keys: unrealized_pnl, unrealized_roi
        or None if trade is closed or missing required fields
    """
    if not trade.is_open or current_price is None:
        return None
    
    position_type = trade.position_type
    
    # LONG positions
    if position_type == 'long':
        if trade.entry_price is None or trade.quantity is None or trade.collateral is None:
            return None
        
        price_change = current_price - trade.entry_price
        gross_pnl = price_change * trade.quantity
        unrealized_pnl = gross_pnl - trade.fee - trade.funding_fees
        
        # Guard against division by zero
        if trade.collateral == 0:
            unrealized_roi = 0.0
        else:
            unrealized_roi = (unrealized_pnl / trade.collateral) * 100
        
        return {
            'unrealized_pnl': round(unrealized_pnl, 2),
            'unrealized_roi': round(unrealized_roi, 2)
        }
    
    # SHORT positions
    elif position_type == 'short':
        if trade.entry_price is None or trade.quantity is None or trade.collateral is None:
            return None
        
        price_change = trade.entry_price - current_price  # Inverted for short
        gross_pnl = price_change * trade.quantity
        unrealized_pnl = gross_pnl - trade.fee - trade.funding_fees
        
        # Guard against division by zero
        if trade.collateral == 0:
            unrealized_roi = 0.0
        else:
            unrealized_roi = (unrealized_pnl / trade.collateral) * 100
        
        return {
            'unrealized_pnl': round(unrealized_pnl, 2),
            'unrealized_roi': round(unrealized_roi, 2)
        }
    
    # Spot positions don't have unrealized P&L in this context
    return None


def calculate_distance_to_liquidation(current_price, liquidation_price, position_type):
    """
    Calculate distance to liquidation as a percentage.
    
    Args:
        current_price: Current market price
        liquidation_price: Liquidation price
        position_type: 'long' or 'short'
    
    Returns:
        Distance as percentage (positive means safe, negative means liquidated)
        or None if invalid inputs
    """
    if current_price is None or liquidation_price is None or current_price == 0:
        return None
    
    if position_type == 'long':
        # Long: distance = (current_price - liquidation_price) / current_price × 100
        distance = ((current_price - liquidation_price) / current_price) * 100
    elif position_type == 'short':
        # Short: distance = (liquidation_price - current_price) / current_price × 100
        distance = ((liquidation_price - current_price) / current_price) * 100
    else:
        return None
    
    return round(distance, 2)
