import { Component, Inject, OnInit, OnDestroy, PLATFORM_ID } from '@angular/core';
import { isPlatformBrowser } from '@angular/common';
import { MAT_DIALOG_DATA, MatDialogRef, } from '@angular/material/dialog';
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

export class FeatureCardComponent implements OnInit, OnDestroy {
  
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
  stackedWrtTarget: boolean = false;
  public originalPlotSize = { width: 400, height: 400 }; // Adjust these values as needed
  isFullScreen: boolean = false;
  private resizeListener: () => void;
  isCategorical: boolean = false;
  tooltipPosition: 'above' | 'below' | 'left' | 'right' = 'above';

  constructor(
    @Inject(MAT_DIALOG_DATA) public data: { fileId: string, columnName: string },
    @Inject(PLATFORM_ID) platformId: Object,
    private dataService: DataService,
    public dialogRef: MatDialogRef<FeatureCardComponent>,
  ) {
    this.isBrowser = isPlatformBrowser(platformId);
    this.resizeListener = () => {
      if (this.isFullScreen) {
        this.createVisualization();
        console.log('FeatureCard constructed with data:', data);
      }
    };
  }

  ngOnInit() {
    this.loadFeatureData();
    if (this.isBrowser) {
      this.loadPlotly().then(() => {
        window.addEventListener('resize', this.resizeListener);
      }).catch(error => {
        console.error('Error loading Plotly:', error);
        this.errorMessage = 'An error occurred while loading the visualization library. Please try again.';
      });
    }
  }

  ngOnDestroy() {
    if (this.isBrowser) {
      window.removeEventListener('resize', this.resizeListener);
    }
  }
  
  loadFeatureData() {
    console.log(`Loading feature data for fileId: ${this.data.fileId}, columnName: ${this.data.columnName}`);
    this.dataService.getFeatureCard(this.data.fileId, this.data.columnName).subscribe(
      (data: FeatureData) => {
        this.featureData = data;
        this.isCategorical = this.featureData.Level_of_Measurement === 'nominal' || this.featureData.Level_of_Measurement === 'ordinal';
        // Disable cleaning options for categorical data
        if (this.isCategorical) {
          this.outlierCleaningEnabled = false;
          this.sparsityCleaningEnabled = false;
        }        
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

  async loadPlotly(): Promise<void> {
    if (!(window as any).Plotly) {
      try {
        const Plotly = await import('plotly.js-dist-min');
        (window as any).Plotly = Plotly.default;
      } catch (error: unknown) {
        console.error('Error loading Plotly:', error);
        if (error instanceof Error) {
          this.errorMessage = `An error occurred while loading the visualization library: ${error.message}. Please try again.`;
        } else {
          this.errorMessage = 'An unknown error occurred while loading the visualization library. Please try again.';
        }
        throw error;
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
  
    const layout: any = {
      title: `Distribution of ${this.featureData.Feature_Name}`,
      xaxis: { 
        title: `Values of ${this.featureData.Feature_Name}`,
        domain: [0, 1]  // Full width for x-axis
      },
      yaxis: {
        title: this.usePercentageYAxis ? 'Percentage' : 'Count',
        domain: [0, 0.85]
      },
      yaxis2: {
        domain: [0.87, 1],
        showticklabels: false,
        zeroline: false,
        showgrid: false,
        title: ''
      },
      height: this.isFullScreen ? window.innerHeight * 0.60 : this.originalPlotSize.height,
      width: this.isFullScreen ? window.innerWidth * 0.90 : this.originalPlotSize.width,
      showlegend: true,
      legend: {
        title: this.stackedWrtTarget ? { text: 'Target Classes' } : undefined,
        traceorder: 'normal'
      },
      // Add margin to accommodate the box plot
      margin: { t: 50, b: 50, l: 50, r: 50 }
    };
  
    if (this.stackedWrtTarget) {
      this.dataService.getStackedFeatureData(this.data.fileId, this.data.columnName).subscribe(
        (stackedData: any) => {
          console.log('Received stacked data:', stackedData);
          let processedData = this.preprocessStackedData(stackedData);
          
          if (this.isNumerical()) {
            //layout.xaxis.rangeslider = {};  // Add a range slider for better navigation
            if (this.outlierCleaningEnabled) {
              processedData = Object.fromEntries(
                Object.entries(processedData).map(([key, value]) => [key, this.cleanOutliers(value as number[])])
              );
            }
            if (this.sparsityCleaningEnabled) {
              processedData = Object.fromEntries(
                Object.entries(processedData).map(([key, value]) => [key, this.cleanSparsity(value as number[])])
              );
            }
          }
          
          this.plotStackedData(processedData, layout);
        },
        error => {
          console.error('Error fetching stacked data:', error);
          this.errorMessage = error.message || 'An error occurred while fetching stacked data';
          this.stackedWrtTarget = false;
          this.plotNonStackedData(this.featureData?.Descriptive_Stats.histogram_data || [], layout);
        }
      );
    } else {
      let histogramData = this.featureData.Descriptive_Stats?.histogram_data || [];
      if (this.isNumerical()) {
        if (this.outlierCleaningEnabled) {
          histogramData = this.cleanOutliers(histogramData) as number[];
        }
        if (this.sparsityCleaningEnabled) {
          histogramData = this.cleanSparsity(histogramData) as number[];
        }
      }
      this.plotNonStackedData(histogramData, layout);
    }
  }

  preprocessStackedData(data: any): any {
    return Object.keys(data).reduce((acc, key) => {
      if (Array.isArray(data[key])) {
        acc[key] = data[key].map((value: any) => 
          value === null || value === 'NaN' ? 'NaN' : parseFloat(value) || 0
        );
      } else {
        acc[key] = Object.entries(data[key]).reduce((innerAcc, [innerKey, innerValue]) => {
          innerAcc[innerKey] = innerValue === null || innerValue === 'NaN' ? 'NaN' : parseFloat(innerValue as string) || 0;
          return innerAcc;
        }, {} as {[key: string]: number | string});
      }
      return acc;
    }, {} as any);
  }

  plotStackedData(stackedData: any, layout: any) {
    console.log('Plotting stacked data:', stackedData);
    console.log('Layout:', layout);
    const Plotly = (window as any).Plotly;
    if (!Plotly) {
      console.error('Plotly is not loaded');
      return;
    }
    if (this.isNumerical()) {
      const histogramTraces: any[] = [];
      const boxplotTraces: any[] = [];
      const colors = Plotly.d3 ? Plotly.d3.schemeCategory10 : ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf'];
      
      Object.keys(stackedData).forEach((targetClass, index) => {
        const data = Array.isArray(stackedData[targetClass]) 
          ? stackedData[targetClass] 
          : Object.values(stackedData[targetClass]);
        const filteredData = data.filter((v: any) => v !== 'NaN' && !isNaN(v)).map(Number);
        
        // Histogram trace
        histogramTraces.push({
          x: filteredData,
          type: 'histogram',
          name: `${targetClass}`,
          opacity: 0.7,
          histnorm: this.usePercentageYAxis ? 'percent' : '',
          marker: { color: colors[index % colors.length] }
        });
        
        // Box plot trace
        boxplotTraces.push({
          x: filteredData,
          type: 'box',
          name: `${targetClass} (Box)`,
          marker: { color: colors[index % colors.length] },
          boxpoints: 'outliers',
          boxmean: true,
          line: { width: 1 },
          yaxis: 'y2',
          showlegend: false
        });
      });
      
      layout.barmode = 'group';
      layout.bargap = 0.1;
      layout.bargroupgap = 0.05;
      layout.showlegend = true;
      layout.legend = { title: this.stackedWrtTarget ? { text: 'Target Classes' } : undefined, traceorder: 'normal' };

      // Adjust layout for combined plot
      layout.yaxis = {
        title: this.usePercentageYAxis ? 'Percentage' : 'Count',
        domain: [0, 0.85]
      };
      layout.yaxis2 = {
        domain: [0.87, 1],
        showticklabels: false,
        zeroline: false,
        showgrid: false,
        title: ''
      };

      const allTraces = [...boxplotTraces, ...histogramTraces];  // Box plots first to be behind histograms

      Plotly.newPlot('visualization', allTraces, layout).catch((error: Error) => {
        console.error('Error plotting data:', error);
        this.errorMessage = 'An error occurred while creating the visualization. Please try again.'});
      console.log('Plotly.newPlot called with:', allTraces, layout);
    } else {
      // For categorical data, create grouped bar chart
      const allCategories = new Set<string>();
      Object.values(stackedData).forEach((data: any) => {
        if (typeof data === 'object') {
          Object.keys(data).forEach(key => allCategories.add(key));
        }
      });
      const categories = Array.from(allCategories);
      const traces = Object.keys(stackedData).map(targetClass => {
        const data = stackedData[targetClass];
        const values = categories.map(cat => (data[cat] || 0));
        const total = values.reduce((sum, val) => sum + (typeof val === 'number' ? val : 0), 0);
        return {
          x: categories,
          y: this.usePercentageYAxis 
          ? values.map(v => (typeof v === 'number' ? (v / total) * 100 : 0))
          : values,
          type: 'bar',
          name: targetClass,
          opacity: 0.7,
        };
      });
      layout.barmode = 'group';
      layout.bargap = 0.15;  // Add some gap between bars
      layout.bargroupgap = 0.1;  // Gap between bars in a group
      layout.showlegend = true;  // Ensure the legend is shown
      layout.legend = { title: this.stackedWrtTarget ? { text: 'Target Classes' } : undefined, traceorder: 'normal' };  // Ensure legend is visible
      layout.yaxis.title = this.usePercentageYAxis ? 'Percentage' : 'Count';
      Plotly.newPlot('visualization', traces, layout);
      console.log('Plotly.newPlot called with:', traces, layout);
    }
  }
  
  plotNonStackedData(histogramData: any[], layout: any) {
    const Plotly = (window as any).Plotly;
    const traces: any[] = [];
    if (this.isNumerical()) {
      if (histogramData && histogramData.length > 0) {
        // Box plot trace (add first to be behind histogram)
        traces.push({
          x: histogramData,
          type: 'box',
          name: 'Box Plot',
          marker: { color: 'rgba(100, 149, 237, 0.7)' },
          boxpoints: 'outliers',
          boxmean: true,
          line: { width: 1 },
          ysrc: 'y2',
          showlegend: false
        });
        // Histogram trace
        traces.push({
          x: histogramData,
          type: 'histogram',
          name: 'Distribution',
          opacity: 0.7,
          histnorm: this.usePercentageYAxis ? 'percent' : '',
          marker: {
            color: 'rgba(100, 149, 237, 0.7)',
            line: {
              color: 'rgba(100, 149, 237, 1)',
              width: 1
            },
          },
        });
      } else {
        console.warn('No histogram data available');
      }
    } else {
      const valueCounts = this.featureData?.Descriptive_Stats.value_counts;
      if (valueCounts && Object.keys(valueCounts).length > 0) {
        const categories = Object.keys(valueCounts);
        const counts = Object.values(valueCounts);
        const total = counts.reduce((sum: number, val: number) => sum + val, 0);
        traces.push({
          x: categories,
          y: this.usePercentageYAxis ? counts.map((v: number) => (v / total) * 100) : counts,
          type: 'bar',
          marker: {
            color: 'rgba(100, 149, 237, 0.7)',
            line: {
              color: 'rgba(100, 149, 237, 1)',
              width: 1
            },
          },
        });
      } else {
        console.warn('No value counts data available');
      }
    }

    // Adjust layout for combined plot
    layout.yaxis = {
      title: this.usePercentageYAxis ? 'Percentage' : 'Count',
      domain: [0, 0.85]
    };
    layout.yaxis2 = {
      domain: [0.87, 1],
      showticklabels: false,
      zeroline: false,
      showgrid: false,
      title: ''
    };

    if (traces.length > 0) {
      Plotly.newPlot('visualization', traces, layout);
    } else {
      console.warn('No data available for visualization');
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
  cleanOutliers(data: number[] | { [key: string]: number }): number[] | { [key: string]: number } {
    if (Array.isArray(data)) {
      const lowerBound = this.getPercentile(data, 5);
      const upperBound = this.getPercentile(data, 95);
      return data.filter(value => value >= lowerBound && value <= upperBound);
    } else {
      const values = Object.values(data);
      const lowerBound = this.getPercentile(values, 5);
      const upperBound = this.getPercentile(values, 95);
      return Object.fromEntries(
        Object.entries(data).filter(([_, value]) => value >= lowerBound && value <= upperBound)
      );
    }
  }

  // Helper function to calculate percentile
  getPercentile(data: number[], percentile: number): number {
    const sortedData = [...data].sort((a, b) => a - b);
    const index = Math.floor((percentile / 100) * sortedData.length);
    return sortedData[index];
  }

  // Function to clean sparsity by removing mode if its ratio is greater than 25%
  cleanSparsity(data: number[] | { [key: string]: number }): number[] | { [key: string]: number } {
    if (Array.isArray(data)) {
      const modeValue = this.getMode(data);
      const modeCount = data.filter(value => value === modeValue).length;
      const modeRatio = (modeCount / data.length) * 100;
      return modeRatio > 25 ? data.filter(value => value !== modeValue) : data;
    } else {
      const values = Object.values(data);
      const modeValue = this.getMode(values);
      const modeCount = values.filter(value => value === modeValue).length;
      const modeRatio = (modeCount / values.length) * 100;
      return modeRatio > 25 
        ? Object.fromEntries(Object.entries(data).filter(([_, value]) => value !== modeValue))
        : data;
    }
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

  toggleFullScreen() {
    this.isFullScreen = !this.isFullScreen;
    if (this.isFullScreen) {
      this.dialogRef.updateSize('100vw', '100vh');
      this.dialogRef.updatePosition({ top: '0', left: '0' });
      this.tooltipPosition = 'above'; // Change tooltip position for full-screen
    } else {
      this.dialogRef.updateSize('400px', 'auto');
      this.dialogRef.updatePosition(); // Reset to default position
      this.tooltipPosition = 'above'; // Reset tooltip position
    }
    setTimeout(() => {
      this.createVisualization();
    }, 0);
  }

  getOutlierCleaningTooltip(): string {
    if (this.isCategorical) {
      return "Outlier cleaning is only available for numerical features";
    } else {
      return "Datapoints falling outside 5th-95th percentile interval are removed from the numerical features.";
    }
  }

  getSparsityCleaningTooltip(): string {
    if (this.isCategorical) {
      return "Sparsity cleaning is only available for numerical features";
    } else {
      return "Datapoints equal the Sparse-Value (mode-value having greater than 25% share) are removed from the numerical features.";
    }
  }

}