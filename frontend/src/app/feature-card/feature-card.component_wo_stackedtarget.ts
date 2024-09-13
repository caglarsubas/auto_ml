import { Component, Inject, OnInit, PLATFORM_ID } from '@angular/core';
import { isPlatformBrowser } from '@angular/common';
import { MAT_DIALOG_DATA, MatDialogRef, } from '@angular/material/dialog';
// Update this import statement to match your project structure
import { DataService } from '../services/data.service';
import { HttpErrorResponse } from '@angular/common/http';
import * as math from 'mathjs';  // Optional: using math.js for easier percentile calculation

interface FeatureData {
  Feature_Name: string;
  Feature_Description: string;
  Level_of_Measurement: string;
  Descriptive_Stats: {
    [key: string]: any;
    histogram_data?: number[];
    value_counts?: { [key: string]: number };
  };
}

@Component({
  selector: 'app-feature-card',
  templateUrl: './feature-card.component.html',
  styleUrls: ['./feature-card.component.css']
})

export class FeatureCardComponent implements OnInit {
  
  numericalStats = [
    'Mean', 'Min', '1st_Quantile', '5th_Quantile', '25th_Q1', 
    '50th_Median', '75th_Q3', '95th_Quantile', '99th_Quantile', 
    'Max', 'Std', 'Skewness', 'Kurtosis'
  ];

  categoricalStats = [
    '#_of_Categories', 'Mode_Value', 'Mode_Ratio', 'Missing_Ratio', '#_of_Outlier_Categories'
  ];

  isBrowser: boolean;
  featureData: FeatureData | null = null;
  errorMessage: string | null = null;
  usePercentageYAxis: boolean = false;
  outlierCleaningEnabled: boolean = false;  // Bound to the 'Outlier Cleaning' checkbox
  sparsityCleaningEnabled: boolean = false;  // Bound to 'Sparsity Cleaning' checkbox

  constructor(
    @Inject(MAT_DIALOG_DATA) public data: { fileId: string, columnName: string },
    @Inject(PLATFORM_ID) platformId: Object,
    private dataService: DataService,
    //public dialogRef: MatDialogRef<FeatureCardComponent>,
  ) {
    this.isBrowser = isPlatformBrowser(platformId);
    console.log('FeatureCard constructed with data:', data);
  }

  ngOnInit() {
    this.loadFeatureData();
  }
  
  loadFeatureData() {
    console.log(`Loading feature data for fileId: ${this.data.fileId}, columnName: ${this.data.columnName}`);
    this.dataService.getFeatureCard(this.data.fileId, this.data.columnName).subscribe(
      (data: FeatureData) => {
        this.featureData = data;
        if (this.isBrowser) {
          this.loadPlotly().then(() => {
            setTimeout(() => {
              this.createVisualization();
            }, 0);
          });
        }
      },
      (error: HttpErrorResponse) => {
        console.error('Error loading feature data:', error);
        if (error.status === 404) {
          this.errorMessage = `File or column not found. Please check the fileId (${this.data.fileId}) and columnName (${this.data.columnName}).`;
        } else {
          this.errorMessage = 'An error occurred while loading the feature data. Please try again.';
        }
      }
    );
  }

  async loadPlotly() {
    if (!(window as any).Plotly) {
      try {
        const Plotly = await import('plotly.js-dist-min');
        (window as any).Plotly = Plotly.default;
      } catch (error) {
        console.error('Error loading Plotly:', error);
      }
    }
  }

  createVisualization() {
    if (!this.featureData) {
      console.error('Feature data is not available');
      return;
    }
  
    const Plotly = (window as any).Plotly;
    if (!Plotly) {
      console.error('Plotly is not loaded');
      return;
    }
  
    const plotElement = document.getElementById('visualization');
    if (!plotElement) {
      console.error('Visualization element not found');
      return;
    }
  
    const plotData: any[] = [];
    const layout: any = {
      title: `Distribution of ${this.featureData.Feature_Name}`,
      xaxis: { 
        title: `Values of ${this.featureData.Feature_Name}` 
      },
      yaxis: {
        title: this.usePercentageYAxis ? 'Percentage' : 'Count'  // Dynamic Y-axis label
      }
    };
  
    let histogramData = this.featureData?.Descriptive_Stats?.histogram_data ?? [];
    
    // Only apply outlier cleaning if the feature is numerical and the checkbox is selected
    if (this.outlierCleaningEnabled && this.isNumerical()) {
      histogramData = this.cleanOutliers(histogramData);
    }
    // Only apply sparsity cleaning if the feature is numerical and the checkbox is selected
    if (this.sparsityCleaningEnabled && this.isNumerical()) {
      histogramData = this.cleanSparsity(histogramData);
    }

    try {
      if (this.isNumerical()) {
        //const histogramData = this.featureData.Descriptive_Stats.histogram_data;
        if (histogramData && histogramData.length > 0) {
          plotData.push({
            x: histogramData,
            type: 'histogram',
            marker: {
              color: 'rgba(100, 149, 237, 0.7)',
              line: {
                color: 'rgba(100, 149, 237, 1)',
                width: 1
              },
            },
            histnorm: this.usePercentageYAxis ? 'percent' : 'count', // Toggle between percentage and count
          });
        } else {
          console.warn('No histogram data available');
        }
      } else { //for categorical features
        const valueCounts = this.featureData.Descriptive_Stats.value_counts;
        if (valueCounts && Object.keys(valueCounts).length > 0) {
          const categories = Object.keys(valueCounts);
          const counts = Object.values(valueCounts);
          plotData.push({
            x: categories,
            y: counts,
            type: 'bar',
            marker: {
              color: 'rgba(100, 149, 237, 0.7)',
              line: {
                color: 'rgba(100, 149, 237, 1)',
                width: 1
              },
              histnorm: this.usePercentageYAxis ? 'percent' : 'count', // Toggle between percentage and count
            }
          });
        } else {
          console.warn('No value counts data available');
        }
      }
  
      if (plotData.length > 0) {
        Plotly.newPlot('visualization', plotData, layout);
      } else {
        console.warn('No data available for visualization');
      }
    } catch (error) {
      console.error('Error creating visualization:', error);
    }
  }

  isNumerical(): boolean {
    return this.featureData?.Level_of_Measurement === 'continuous' || this.featureData?.Level_of_Measurement === 'cardinal';
  }

  getStats(): string[] {
    return this.isNumerical() ? this.numericalStats : this.categoricalStats;
  }

  getStatValue(stat: string): string | number {
    const value = this.featureData?.Descriptive_Stats[stat];
    return value !== undefined ? value : 'N/A';
  }

  // Function to clean outliers below 5th and above 95th percentiles
  cleanOutliers(data: number[]): number[] {
    const lowerBound = this.getPercentile(data, 5);
    const upperBound = this.getPercentile(data, 95);

    return data.filter(value => value >= lowerBound && value <= upperBound);
  }

  // Helper function to calculate percentile
  getPercentile(data: number[], percentile: number): number {
    const sortedData = [...data].sort((a, b) => a - b);
    const index = Math.floor((percentile / 100) * sortedData.length);
    return sortedData[index];
  }

  // Function to clean sparsity by removing mode if its ratio is greater than 25%
  cleanSparsity(data: number[]): number[] {
    const modeValue = this.getMode(data);
    const modeCount = data.filter(value => value === modeValue).length;
    const modeRatio = (modeCount / data.length) * 100;

    // Only remove the mode if its ratio is greater than 25%
    if (modeRatio > 25) {
      return data.filter(value => value !== modeValue);
    }

    return data;  // Return the original data if mode-ratio is not greater than 25%
  }

  // Helper function to calculate mode
  getMode(data: number[]): number {
    const frequencyMap: { [key: number]: number } = {};

    // Create a frequency map for the data
    data.forEach(value => {
      if (!frequencyMap[value]) {
        frequencyMap[value] = 0;
      }
      frequencyMap[value]++;
    });

    // Find the mode (most frequent value)
    let mode = data[0];
    let maxCount = frequencyMap[mode];

    for (const key in frequencyMap) {
      if (frequencyMap[key] > maxCount) {
        mode = +key;  // Convert key to number and assign to mode
        maxCount = frequencyMap[key];
      }
    }

    return mode;
  }
}