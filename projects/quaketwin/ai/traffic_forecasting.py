#!/usr/bin/env python3
"""
FGCU Traffic Forecasting AI Models
Advanced machine learning models for traffic prediction and analysis
"""

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_squared_error, r2_score
import datetime
import logging
import pickle
import os
from typing import Dict, List, Tuple, Optional
import warnings
warnings.filterwarnings('ignore')

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class FGCUTrafficForecaster:
    """
    Advanced traffic forecasting system for FGCU campus
    Uses multiple ML models for accurate predictions
    """
    
    def __init__(self, model_path: Optional[str] = None):
        """Initialize the forecasting system"""
        self.models = {}
        self.scalers = {}
        self.model_metrics = {}
        self.is_trained = False
        self.model_path = model_path or "traffic_models.pkl"
        
        # FGCU campus coordinates
        self.fgcu_bounds = {
            'south': 26.4385,
            'west': -81.7950,
            'north': 26.4950,
            'east': -81.7350
        }
        
        logger.info("🤖 FGCU Traffic Forecaster initialized")
    
    def generate_synthetic_data(self, days: int = 90) -> pd.DataFrame:
        """
        Generate realistic synthetic traffic data for FGCU
        Simulates patterns based on university schedules
        """
        logger.info(f"Generating {days} days of synthetic traffic data...")
        
        # Time series setup
        start_date = datetime.datetime.now() - datetime.timedelta(days=days)
        date_range = pd.date_range(start=start_date, periods=days*24, freq='H')
        
        data = []
        
        for timestamp in date_range:
            hour = timestamp.hour
            day_of_week = timestamp.weekday()  # 0=Monday, 6=Sunday
            month = timestamp.month
            
            # Base traffic patterns
            base_volume = self._get_base_volume(hour, day_of_week, month)
            
            # Add realistic noise and variations
            volume = max(10, int(base_volume * np.random.normal(1.0, 0.15)))
            speed = self._calculate_speed_from_volume(volume)
            
            # Weather impact (random weather events)
            if np.random.random() < 0.1:  # 10% chance of weather impact
                weather_factor = np.random.uniform(0.6, 0.9)
                volume = int(volume * weather_factor)
                speed = speed * np.random.uniform(0.7, 0.9)
            
            # Special events (random events affecting traffic)
            if np.random.random() < 0.05:  # 5% chance of special event
                event_factor = np.random.uniform(1.2, 2.0)
                volume = int(volume * event_factor)
                speed = speed * np.random.uniform(0.5, 0.8)
            
            data.append({
                'timestamp': timestamp,
                'hour': hour,
                'day_of_week': day_of_week,
                'month': month,
                'is_weekend': day_of_week >= 5,
                'is_holiday': self._is_holiday(timestamp),
                'volume': volume,
                'speed': round(speed, 1),
                'density': round(volume / max(speed, 1), 2),
                'segment_id': np.random.choice(['bh_griffin_pkwy', 'fgcu_blvd', 'campus_loop'])
            })
        
        df = pd.DataFrame(data)
        logger.info(f"Generated {len(df)} traffic records")
        return df
    
    def _get_base_volume(self, hour: int, day_of_week: int, month: int) -> float:
        """Calculate base traffic volume based on time patterns"""
        
        # Hourly patterns (university schedule based)
        hourly_factors = {
            0: 0.1, 1: 0.05, 2: 0.05, 3: 0.05, 4: 0.05, 5: 0.1,
            6: 0.3, 7: 0.8, 8: 1.5, 9: 1.0, 10: 0.7, 11: 0.9,
            12: 1.2, 13: 1.0, 14: 1.1, 15: 1.3, 16: 1.6, 17: 1.4,
            18: 0.9, 19: 0.7, 20: 0.5, 21: 0.4, 22: 0.3, 23: 0.2
        }
        
        # Day of week factors
        dow_factors = {
            0: 1.0,  # Monday
            1: 1.1,  # Tuesday
            2: 1.1,  # Wednesday
            3: 1.0,  # Thursday
            4: 0.9,  # Friday
            5: 0.3,  # Saturday
            6: 0.2   # Sunday
        }
        
        # Monthly factors (academic calendar)
        monthly_factors = {
            1: 1.0,   # January - Spring semester
            2: 1.1,   # February
            3: 1.1,   # March
            4: 1.0,   # April
            5: 0.3,   # May - Summer break
            6: 0.2,   # June
            7: 0.2,   # July
            8: 0.8,   # August - Fall semester prep
            9: 1.1,   # September - Fall semester
            10: 1.1,  # October
            11: 1.0,  # November
            12: 0.5   # December - Winter break
        }
        
        base = 300  # Base volume
        hour_factor = hourly_factors.get(hour, 0.5)
        dow_factor = dow_factors.get(day_of_week, 0.5)
        month_factor = monthly_factors.get(month, 1.0)
        
        return base * hour_factor * dow_factor * month_factor
    
    def _calculate_speed_from_volume(self, volume: int) -> float:
        """Calculate speed based on traffic volume (inverse relationship)"""
        if volume < 50:
            return np.random.uniform(45, 55)
        elif volume < 150:
            return np.random.uniform(35, 45)
        elif volume < 300:
            return np.random.uniform(25, 35)
        elif volume < 500:
            return np.random.uniform(15, 25)
        else:
            return np.random.uniform(10, 15)
    
    def _is_holiday(self, date: datetime.datetime) -> bool:
        """Check if date is a holiday or academic break"""
        # Simplified holiday detection
        holidays = [
            (1, 1),   # New Year
            (7, 4),   # Independence Day
            (12, 25), # Christmas
        ]
        
        month_day = (date.month, date.day)
        return month_day in holidays
    
    def prepare_features(self, df: pd.DataFrame) -> Tuple[np.ndarray, np.ndarray]:
        """Prepare features for machine learning models"""
        logger.info("Preparing features for ML models...")
        
        # Create additional features
        df['hour_sin'] = np.sin(2 * np.pi * df['hour'] / 24)
        df['hour_cos'] = np.cos(2 * np.pi * df['hour'] / 24)
        df['day_sin'] = np.sin(2 * np.pi * df['day_of_week'] / 7)
        df['day_cos'] = np.cos(2 * np.pi * df['day_of_week'] / 7)
        df['month_sin'] = np.sin(2 * np.pi * df['month'] / 12)
        df['month_cos'] = np.cos(2 * np.pi * df['month'] / 12)
        
        # Feature matrix
        feature_columns = [
            'hour', 'day_of_week', 'month', 'is_weekend', 'is_holiday',
            'hour_sin', 'hour_cos', 'day_sin', 'day_cos', 'month_sin', 'month_cos'
        ]
        
        X = df[feature_columns].values
        y = df['volume'].values
        
        logger.info(f"Features shape: {X.shape}, Target shape: {y.shape}")
        return X, y
    
    def train_models(self, df: Optional[pd.DataFrame] = None) -> Dict[str, float]:
        """Train multiple ML models on traffic data"""
        logger.info("🎯 Training traffic forecasting models...")
        
        if df is None:
            df = self.generate_synthetic_data(days=90)
        
        # Prepare data
        X, y = self.prepare_features(df)
        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
        
        # Scale features
        scaler = StandardScaler()
        X_train_scaled = scaler.fit_transform(X_train)
        X_test_scaled = scaler.transform(X_test)
        self.scalers['standard'] = scaler
        
        # Define models
        models = {
            'random_forest': RandomForestRegressor(
                n_estimators=100, 
                random_state=42,
                n_jobs=-1
            ),
            'gradient_boosting': GradientBoostingRegressor(
                n_estimators=100,
                learning_rate=0.1,
                max_depth=6,
                random_state=42
            )
        }
        
        results = {}
        
        # Train and evaluate each model
        for name, model in models.items():
            logger.info(f"Training {name}...")
            
            # Train model
            if name == 'random_forest':
                model.fit(X_train, y_train)
                y_pred = model.predict(X_test)
            else:
                model.fit(X_train_scaled, y_train)
                y_pred = model.predict(X_test_scaled)
            
            # Calculate metrics
            mse = mean_squared_error(y_test, y_pred)
            rmse = np.sqrt(mse)
            r2 = r2_score(y_test, y_pred)
            
            # Store model and metrics
            self.models[name] = model
            self.model_metrics[name] = {
                'mse': mse,
                'rmse': rmse,
                'r2': r2,
                'accuracy': r2
            }
            
            results[name] = r2
            logger.info(f"{name}: R² = {r2:.4f}, RMSE = {rmse:.2f}")
        
        self.is_trained = True
        
        # Save models
        self.save_models()
        
        logger.info("✅ Model training completed!")
        return results
    
    def predict_traffic(self, segment_id: str, hours_ahead: int = 24) -> List[Dict]:
        """Predict traffic for specified hours ahead"""
        if not self.is_trained and not self.load_models():
            logger.warning("No trained models available, training new ones...")
            self.train_models()
        
        # Generate future timestamps
        now = datetime.datetime.now()
        predictions = []
        
        for hour in range(1, hours_ahead + 1):
            future_time = now + datetime.timedelta(hours=hour)
            
            # Prepare features
            features = np.array([[
                future_time.hour,
                future_time.weekday(),
                future_time.month,
                1 if future_time.weekday() >= 5 else 0,  # is_weekend
                1 if self._is_holiday(future_time) else 0,  # is_holiday
                np.sin(2 * np.pi * future_time.hour / 24),  # hour_sin
                np.cos(2 * np.pi * future_time.hour / 24),  # hour_cos
                np.sin(2 * np.pi * future_time.weekday() / 7),  # day_sin
                np.cos(2 * np.pi * future_time.weekday() / 7),  # day_cos
                np.sin(2 * np.pi * future_time.month / 12),  # month_sin
                np.cos(2 * np.pi * future_time.month / 12),  # month_cos
            ]])
            
            # Get predictions from both models
            rf_pred = self.models['random_forest'].predict(features)[0]
            
            # Scale features for gradient boosting
            features_scaled = self.scalers['standard'].transform(features)
            gb_pred = self.models['gradient_boosting'].predict(features_scaled)[0]
            
            # Ensemble prediction (weighted average)
            rf_weight = self.model_metrics['random_forest']['r2']
            gb_weight = self.model_metrics['gradient_boosting']['r2']
            total_weight = rf_weight + gb_weight
            
            ensemble_pred = (rf_pred * rf_weight + gb_pred * gb_weight) / total_weight
            
            # Ensure reasonable bounds
            final_pred = max(10, min(800, int(ensemble_pred)))
            
            # Calculate confidence based on model agreement
            agreement = 1 - abs(rf_pred - gb_pred) / max(rf_pred, gb_pred, 1)
            confidence = min(0.95, max(0.6, agreement * 0.9))
            
            predictions.append({
                'timestamp': future_time.isoformat(),
                'hour_ahead': hour,
                'predicted_volume': final_pred,
                'confidence': round(confidence, 3),
                'rf_prediction': int(rf_pred),
                'gb_prediction': int(gb_pred)
            })
        
        return predictions
    
    def get_model_performance(self) -> Dict:
        """Get performance metrics for all trained models"""
        if not self.is_trained:
            return {"error": "No trained models available"}
        
        return {
            'models': self.model_metrics,
            'best_model': max(self.model_metrics.items(), key=lambda x: x[1]['r2'])[0],
            'ensemble_available': len(self.models) > 1
        }
    
    def save_models(self) -> bool:
        """Save trained models to disk"""
        try:
            model_data = {
                'models': self.models,
                'scalers': self.scalers,
                'metrics': self.model_metrics,
                'is_trained': self.is_trained,
                'timestamp': datetime.datetime.now().isoformat()
            }
            
            with open(self.model_path, 'wb') as f:
                pickle.dump(model_data, f)
            
            logger.info(f"Models saved to {self.model_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to save models: {e}")
            return False
    
    def load_models(self) -> bool:
        """Load trained models from disk"""
        try:
            if not os.path.exists(self.model_path):
                return False
            
            with open(self.model_path, 'rb') as f:
                model_data = pickle.load(f)
            
            self.models = model_data['models']
            self.scalers = model_data['scalers']
            self.model_metrics = model_data['metrics']
            self.is_trained = model_data['is_trained']
            
            logger.info(f"Models loaded from {self.model_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to load models: {e}")
            return False


def main():
    """Test the forecasting system"""
    logger.info("🚀 Testing FGCU Traffic Forecasting System")
    
    # Initialize forecaster
    forecaster = FGCUTrafficForecaster()
    
    # Train models
    results = forecaster.train_models()
    
    # Print results
    print("\n🎯 Model Training Results:")
    print("-" * 40)
    for model_name, r2_score in results.items():
        print(f"{model_name:20} R² = {r2_score:.4f}")
    
    # Test predictions
    print("\n🔮 24-Hour Traffic Forecast:")
    print("-" * 50)
    predictions = forecaster.predict_traffic("fgcu_blvd", hours_ahead=6)
    
    for pred in predictions:
        time_str = datetime.datetime.fromisoformat(pred['timestamp']).strftime('%H:%M')
        print(f"{time_str} | Volume: {pred['predicted_volume']:3d} | "
              f"Confidence: {pred['confidence']:.2f}")
    
    # Show performance
    performance = forecaster.get_model_performance()
    print(f"\n📊 Best Model: {performance['best_model']}")
    
    print("\n✅ Forecasting system test completed!")


if __name__ == "__main__":
    main()