import json
import sys
import os
from typing import Dict, Any, Optional

# Add the FundScorer class 
class FundScorer:
    """Implements the fund scoring system as per the PDF guidelines"""
    
    def __init__(self):
        # Risk categorization thresholds
        self.risk_thresholds = {
            'low': (0, 30),
            'medium': (31, 60),
            'high': (61, 100)
        }
        
        # Performance scoring weights
        self.performance_weights = {
            'sharpe_ratio': 0.39,
            'annualized_return': 0.25,
            'sortino_ratio': 0.16,
            'treynor_ratio': 0.12,
            'up_down_ratio': 0.08,
            'max_drawdown': -0.07  # Penalty
        }
        
        # Risk scoring weights
        self.risk_weights = {
            'standard_deviation': 0.40,
            'beta': 0.30,
            'max_drawdown': 0.30
        }
    
    def normalize_value(self, value: float, min_val: float, max_val: float) -> float:
        """Normalize value using (X-Min)/(Max-Min) formula"""
        if max_val == min_val:
            return 0.0
        return (value - min_val) / (max_val - min_val)
    
    def safe_float(self, value: Any) -> Optional[float]:
        """Safely convert value to float"""
        if value is None or value == 'N/A' or value == '':
            return None
        try:
            if isinstance(value, str):
                # Remove percentage signs and other characters
                cleaned = value.replace('%', '').replace(',', '').strip()
                if cleaned == '' or cleaned == 'N/A':
                    return None
                return float(cleaned)
            return float(value)
        except (ValueError, TypeError):
            return None
    
    def get_risk_category(self, risk_score: float) -> str:
        """Determine risk category based on score"""
        if risk_score <= 30:
            return 'Low Risk'
        elif risk_score <= 60:
            return 'Medium Risk'
        else:
            return 'High Risk'
    
    def calculate_risk_score(self, fund_data: Dict[str, Any], all_funds_data: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate risk score for a fund"""
        try:
            # Extract risk metrics
            std_dev = self.safe_float(fund_data.get('Standard Deviation', {}).get('3y', 'N/A'))
            beta = self.safe_float(fund_data.get('Beta', {}).get('3y', 'N/A'))
            max_drawdown = self.safe_float(fund_data.get('Max Drawdown', {}).get('3y', 'N/A'))
            
            if any(val is None for val in [std_dev, beta, max_drawdown]):
                return {'risk_score': None, 'risk_category': 'Unknown', 'components': {}}
            
            # Get min/max values across all funds
            all_std_devs = [self.safe_float(fund.get('Standard Deviation', {}).get('3y', 'N/A')) 
                           for fund in all_funds_data.values()]
            all_betas = [self.safe_float(fund.get('Beta', {}).get('3y', 'N/A')) 
                        for fund in all_funds_data.values()]
            all_drawdowns = [self.safe_float(fund.get('Max Drawdown', {}).get('3y', 'N/A')) 
                           for fund in all_funds_data.values()]
            
            # Filter out None values
            all_std_devs = [x for x in all_std_devs if x is not None]
            all_betas = [x for x in all_betas if x is not None]
            all_drawdowns = [x for x in all_drawdowns if x is not None]
            
            if not all([all_std_devs, all_betas, all_drawdowns]):
                return {'risk_score': None, 'risk_category': 'Unknown', 'components': {}}
            
            # Normalize each component
            std_dev_norm = self.normalize_value(std_dev, min(all_std_devs), max(all_std_devs))
            beta_norm = self.normalize_value(beta, min(all_betas), max(all_betas))
            drawdown_norm = self.normalize_value(max_drawdown, min(all_drawdowns), max(all_drawdowns))
            
            # Calculate weighted risk score
            risk_score = (
                std_dev_norm * self.risk_weights['standard_deviation'] +
                beta_norm * self.risk_weights['beta'] +
                drawdown_norm * self.risk_weights['max_drawdown']
            ) * 100
            
            # Determine risk category
            risk_category = self.get_risk_category(risk_score)
            
            return {
                'risk_score': round(risk_score, 2),
                'risk_category': risk_category,
                'components': {
                    'std_dev_normalized': round(std_dev_norm, 4),
                    'beta_normalized': round(beta_norm, 4),
                    'drawdown_normalized': round(drawdown_norm, 4)
                }
            }
            
        except Exception as e:
            print(f"Error calculating risk score: {e}")
            return {'risk_score': None, 'risk_category': 'Unknown', 'components': {}}
    
    def calculate_performance_score(self, fund_data: Dict[str, Any], all_funds_data: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate performance score for a fund"""
        try:
            # Extract performance metrics
            sharpe = self.safe_float(fund_data.get('Sharpe Ratio', {}).get('3y', 'N/A'))
            annual_return = self.safe_float(fund_data.get('Mean Annual Return', {}).get('3y', 'N/A'))
            sortino = self.safe_float(fund_data.get('Sortino Ratio', {}).get('3y', 'N/A'))
            treynor = self.safe_float(fund_data.get('Treynor Ratio', {}).get('3y', 'N/A'))
            up_down_ratio = self.safe_float(fund_data.get('Up/Down Ratio', {}).get('3y', 'N/A'))
            max_drawdown = self.safe_float(fund_data.get('Max Drawdown', {}).get('3y', 'N/A'))
            
            # Get all values for normalization
            all_sharpe = [self.safe_float(fund.get('Sharpe Ratio', {}).get('3y', 'N/A')) 
                         for fund in all_funds_data.values()]
            all_returns = [self.safe_float(fund.get('Mean Annual Return', {}).get('3y', 'N/A')) 
                          for fund in all_funds_data.values()]
            all_sortino = [self.safe_float(fund.get('Sortino Ratio', {}).get('3y', 'N/A')) 
                          for fund in all_funds_data.values()]
            all_treynor = [self.safe_float(fund.get('Treynor Ratio', {}).get('3y', 'N/A')) 
                          for fund in all_funds_data.values()]
            all_up_down = [self.safe_float(fund.get('Up/Down Ratio', {}).get('3y', 'N/A')) 
                          for fund in all_funds_data.values()]
            all_drawdowns = [self.safe_float(fund.get('Max Drawdown', {}).get('3y', 'N/A')) 
                           for fund in all_funds_data.values()]
            
            # Filter out None values
            all_sharpe = [x for x in all_sharpe if x is not None]
            all_returns = [x for x in all_returns if x is not None]
            all_sortino = [x for x in all_sortino if x is not None]
            all_treynor = [x for x in all_treynor if x is not None]
            all_up_down = [x for x in all_up_down if x is not None]
            all_drawdowns = [x for x in all_drawdowns if x is not None]
            
            # Calculate normalized components
            components = {}
            score = 0
            
            if sharpe is not None and all_sharpe:
                sharpe_norm = self.normalize_value(sharpe, min(all_sharpe), max(all_sharpe))
                components['sharpe_normalized'] = round(sharpe_norm, 4)
                score += sharpe_norm * self.performance_weights['sharpe_ratio']
            
            if annual_return is not None and all_returns:
                return_norm = self.normalize_value(annual_return, min(all_returns), max(all_returns))
                components['return_normalized'] = round(return_norm, 4)
                score += return_norm * self.performance_weights['annualized_return']
            
            if sortino is not None and all_sortino:
                sortino_norm = self.normalize_value(sortino, min(all_sortino), max(all_sortino))
                components['sortino_normalized'] = round(sortino_norm, 4)
                score += sortino_norm * self.performance_weights['sortino_ratio']
            
            if treynor is not None and all_treynor:
                treynor_norm = self.normalize_value(treynor, min(all_treynor), max(all_treynor))
                components['treynor_normalized'] = round(treynor_norm, 4)
                score += treynor_norm * self.performance_weights['treynor_ratio']
            
            if up_down_ratio is not None and all_up_down:
                up_down_norm = self.normalize_value(up_down_ratio, min(all_up_down), max(all_up_down))
                components['up_down_normalized'] = round(up_down_norm, 4)
                score += up_down_norm * self.performance_weights['up_down_ratio']
            
            if max_drawdown is not None and all_drawdowns:
                # For max drawdown, higher is worse, so we penalize
                drawdown_norm = self.normalize_value(max_drawdown, min(all_drawdowns), max(all_drawdowns))
                components['drawdown_penalty'] = round(drawdown_norm, 4)
                score += drawdown_norm * self.performance_weights['max_drawdown']  # Negative weight
            
            performance_score = score * 100
            
            return {
                'performance_score': round(performance_score, 2),
                'components': components
            }
            
        except Exception as e:
            print(f"Error calculating performance score: {e}")
            return {'performance_score': None, 'components': {}}
    
    def score_all_funds(self, funds_data: Dict[str, Any]) -> Dict[str, Any]:
        """Score all funds and return results"""
        results = {}
        
        for ticker, fund_info in funds_data.items():
            fund_data = fund_info.get('Metrics', {})
            
            risk_result = self.calculate_risk_score(fund_data, 
                                                  {t: info.get('Metrics', {}) for t, info in funds_data.items()})
            perf_result = self.calculate_performance_score(fund_data, 
                                                         {t: info.get('Metrics', {}) for t, info in funds_data.items()})
            
            results[ticker] = {
                'category': fund_info.get('Category', 'Unknown'),
                'risk_analysis': risk_result,
                'performance_analysis': perf_result,
                'raw_metrics': fund_data
            }
        
        return results

def format_value(value, default="N/A"):
    """Safely format values for display, handling None values"""
    if value is None:
        return default
    return str(value)

def test_scoring_functionality():
    """Test the fund scoring functionality"""
    
    # Check if the fund data file exists
    fund_data_file = 'Data/fund_risk_metrics.json'
    if not os.path.exists(fund_data_file):
        print(f"❌ Error: {fund_data_file} not found!")
        print("Please make sure the file exists in the Data directory.")
        return
    
    try:
        # Load fund data
        print("📊 Loading fund data...")
        with open(fund_data_file, 'r') as f:
            funds_data = json.load(f)
        
        print(f"✅ Loaded {len(funds_data)} funds")
        
        # Initialize scorer
        print("\n🔢 Initializing fund scorer...")
        scorer = FundScorer()
        
        # Score all funds
        print("🎯 Scoring all funds...")
        scored_funds = scorer.score_all_funds(funds_data)
        
        # Display results
        print("\n" + "="*80)
        print("📈 FUND SCORING RESULTS")
        print("="*80)
        
        # Sort funds by performance score (descending), handling None values
        sorted_funds = sorted(
            scored_funds.items(),
            key=lambda x: x[1]['performance_analysis'].get('performance_score', -999) if x[1]['performance_analysis'].get('performance_score') is not None else -999,
            reverse=True
        )
        
        print(f"\n{'Ticker':<8} {'Category':<15} {'Risk Score':<12} {'Risk Level':<12} {'Perf Score':<12}")
        print("-" * 80)
        
        for ticker, data in sorted_funds:
            risk_score = format_value(data['risk_analysis'].get('risk_score'))
            risk_category = format_value(data['risk_analysis'].get('risk_category', 'Unknown'))
            perf_score = format_value(data['performance_analysis'].get('performance_score'))
            category = format_value(data.get('category', 'Unknown'))
            
            print(f"{ticker:<8} {category:<15} {risk_score:<12} {risk_category:<12} {perf_score:<12}")
        
        # Show detailed analysis for top 3 funds
        print("\n" + "="*80)
        print("🔍 DETAILED ANALYSIS - TOP 3 FUNDS")
        print("="*80)
        
        for i, (ticker, data) in enumerate(sorted_funds[:3]):
            print(f"\n{i+1}. {ticker} - {data.get('category', 'Unknown')}")
            print("-" * 40)
            
            # Risk analysis
            risk_analysis = data['risk_analysis']
            print(f"Risk Score: {format_value(risk_analysis.get('risk_score'))}")
            print(f"Risk Category: {format_value(risk_analysis.get('risk_category', 'Unknown'))}")
            
            if risk_analysis.get('components'):
                components = risk_analysis['components']
                print(f"  • Std Dev (normalized): {format_value(components.get('std_dev_normalized'))}")
                print(f"  • Beta (normalized): {format_value(components.get('beta_normalized'))}")
                print(f"  • Max Drawdown (normalized): {format_value(components.get('drawdown_normalized'))}")
            
            # Performance analysis
            perf_analysis = data['performance_analysis']
            print(f"Performance Score: {format_value(perf_analysis.get('performance_score'))}")
            
            if perf_analysis.get('components'):
                components = perf_analysis['components']
                print("  Performance Components:")
                for key, value in components.items():
                    print(f"    • {key}: {format_value(value)}")
        
        # Show funds by risk category
        print("\n" + "="*80)
        print("🎯 FUNDS BY RISK CATEGORY")
        print("="*80)
        
        risk_categories = {'Low Risk': [], 'Medium Risk': [], 'High Risk': [], 'Unknown': []}
        
        for ticker, data in scored_funds.items():
            risk_category = data['risk_analysis'].get('risk_category', 'Unknown')
            risk_categories[risk_category].append(ticker)
        
        for category, tickers in risk_categories.items():
            if tickers:
                print(f"\n{category}: {', '.join(tickers)}")
        
        # Save results to file
        output_file = 'fund_scoring_results.json'
        with open(output_file, 'w') as f:
            json.dump(scored_funds, f, indent=2)
        
        print(f"\n✅ Results saved to {output_file}")
        print(f"📊 Successfully scored {len(scored_funds)} funds!")
        
    except FileNotFoundError:
        print(f"❌ Error: Could not find {fund_data_file}")
        print("Please ensure the file exists and the path is correct.")
    except json.JSONDecodeError:
        print(f"❌ Error: Invalid JSON in {fund_data_file}")
        print("Please check that the file contains valid JSON data.")
    except Exception as e:
        print(f"❌ Error during scoring: {str(e)}")
        import traceback
        traceback.print_exc()

def test_individual_fund(ticker: str):
    """Test scoring for a specific fund"""
    fund_data_file = 'Data/fund_risk_metrics.json'
    
    if not os.path.exists(fund_data_file):
        print(f"❌ Error: {fund_data_file} not found!")
        return
    
    try:
        with open(fund_data_file, 'r') as f:
            funds_data = json.load(f)
        
        if ticker not in funds_data:
            print(f"❌ Error: Fund {ticker} not found in data!")
            available_tickers = list(funds_data.keys())[:10]  # Show first 10
            print(f"Available tickers (first 10): {available_tickers}")
            return
        
        scorer = FundScorer()
        scored_funds = scorer.score_all_funds(funds_data)
        
        fund_data = scored_funds[ticker]
        
        print(f"\n📊 DETAILED ANALYSIS FOR {ticker}")
        print("="*50)
        print(f"Category: {fund_data.get('category', 'Unknown')}")
        
        # Risk Analysis
        risk_analysis = fund_data['risk_analysis']
        print(f"\n🎯 Risk Analysis:")
        print(f"  Risk Score: {format_value(risk_analysis.get('risk_score'))}")
        print(f"  Risk Category: {format_value(risk_analysis.get('risk_category', 'Unknown'))}")
        
        if risk_analysis.get('components'):
            print("  Components:")
            for key, value in risk_analysis['components'].items():
                print(f"    • {key}: {format_value(value)}")
        
        # Performance Analysis
        perf_analysis = fund_data['performance_analysis']
        print(f"\n📈 Performance Analysis:")
        print(f"  Performance Score: {format_value(perf_analysis.get('performance_score'))}")
        
        if perf_analysis.get('components'):
            print("  Components:")
            for key, value in perf_analysis['components'].items():
                print(f"    • {key}: {format_value(value)}")
        
        # Raw Metrics
        raw_metrics = fund_data['raw_metrics']
        print(f"\n📋 Raw Metrics (3-year):")
        for metric, periods in raw_metrics.items():
            if isinstance(periods, dict) and '3y' in periods:
                print(f"  {metric}: {periods['3y']}")
        
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    print("🚀 ORION Fund Scoring Test")
    print("="*50)
    
    if len(sys.argv) > 1:
        # Test specific fund
        ticker = sys.argv[1].upper()
        test_individual_fund(ticker)
    else:
        # Test all funds
        test_scoring_functionality()