"""
Data preprocessing utilities for STI prediction pipeline.
"""
import numpy as np
import pandas as pd
from typing import Dict, List, Any, Tuple
from .models import DataCleaningRule, FeatureTransformation


class DataPreprocessor:
    """
    Handles data cleaning, validation, and feature engineering
    for the STI prediction pipeline.
    """
    
    def __init__(self):
        self.cleaning_rules = DataCleaningRule.objects.filter(is_active=True)
        self.transformations = FeatureTransformation.objects.filter(is_active=True)
    
    def clean_dataframe(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, List[Dict]]:
        """
        Apply all active cleaning rules to a dataframe.
        Returns cleaned df and list of applied actions.
        """
        actions = []
        original_rows = len(df)
        
        for rule in self.cleaning_rules:
            if rule.field_name not in df.columns:
                continue
            
            if rule.rule_type == 'missing':
                missing_count = df[rule.field_name].isna().sum()
                if missing_count > 0:
                    if rule.action == 'fill_mean':
                        df[rule.field_name].fillna(df[rule.field_name].mean(), inplace=True)
                    elif rule.action == 'fill_median':
                        df[rule.field_name].fillna(df[rule.field_name].median(), inplace=True)
                    elif rule.action == 'fill_mode':
                        df[rule.field_name].fillna(df[rule.field_name].mode()[0], inplace=True)
                    elif rule.action == 'drop':
                        df = df.dropna(subset=[rule.field_name])
                    
                    actions.append({
                        'rule': rule.name,
                        'action': rule.action,
                        'affected_rows': int(missing_count),
                    })
            
            elif rule.rule_type == 'outlier':
                Q1 = df[rule.field_name].quantile(0.25)
                Q3 = df[rule.field_name].quantile(0.75)
                IQR = Q3 - Q1
                outlier_mask = (df[rule.field_name] < (Q1 - 1.5 * IQR)) | (df[rule.field_name] > (Q3 + 1.5 * IQR))
                outlier_count = outlier_mask.sum()
                
                if outlier_count > 0 and rule.action == 'flag':
                    df[f'{rule.field_name}_outlier'] = outlier_mask
                
                actions.append({
                    'rule': rule.name,
                    'action': rule.action,
                    'affected_rows': int(outlier_count),
                })
        
        final_rows = len(df)
        actions.append({
            'rule': 'total',
            'action': 'summary',
            'original_rows': original_rows,
            'final_rows': final_rows,
            'dropped_rows': original_rows - final_rows,
        })
        
        return df, actions
    
    def engineer_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Apply feature transformations.
        """
        for transform in self.transformations:
            if transform.source_field not in df.columns:
                continue
            
            params = transform.parameters or {}
            
            if transform.transform_type == 'log':
                df[transform.output_field] = np.log1p(df[transform.source_field].clip(lower=0))
            
            elif transform.transform_type == 'sqrt':
                df[transform.output_field] = np.sqrt(df[transform.source_field].clip(lower=0))
            
            elif transform.transform_type == 'scale':
                min_val = df[transform.source_field].min()
                max_val = df[transform.source_field].max()
                if max_val > min_val:
                    df[transform.output_field] = (df[transform.source_field] - min_val) / (max_val - min_val)
            
            elif transform.transform_type == 'standardize':
                mean = df[transform.source_field].mean()
                std = df[transform.source_field].std()
                if std > 0:
                    df[transform.output_field] = (df[transform.source_field] - mean) / std
            
            elif transform.transform_type == 'binning':
                bins = params.get('bins', 4)
                labels = params.get('labels', None)
                df[transform.output_field] = pd.cut(
                    df[transform.source_field], 
                    bins=bins, 
                    labels=labels
                )
        
        # STI-specific engineered features
        if 'num_partners_12m' in df.columns and 'condom_use_freq' in df.columns:
            df['risk_exposure_index'] = df['num_partners_12m'] * (1 - df['condom_use_freq'])
        
        if 'age' in df.columns:
            df['age_group_encoded'] = pd.cut(
                df['age'],
                bins=[0, 15, 20, 25, 30, 35, 40, 50, 100],
                labels=[0, 1, 2, 3, 4, 5, 6, 7]
            )
        
        return df
    
    def validate_patient_data(self, data: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """
        Validate a single patient record before prediction.
        """
        errors = []
        
        required_fields = ['age', 'gender', 'num_partners_12m']
        for field in required_fields:
            if field not in data or data[field] is None:
                errors.append(f"Missing required field: {field}")
        
        if 'age' in data and (data['age'] < 10 or data['age'] > 120):
            errors.append("Age must be between 10 and 120")
        
        if 'num_partners_12m' in data and data['num_partners_12m'] < 0:
            errors.append("Number of partners cannot be negative")
        
        if 'condom_use_freq' in data and not (0 <= data['condom_use_freq'] <= 1):
            errors.append("Condom use frequency must be between 0 and 1")
        
        return len(errors) == 0, errors