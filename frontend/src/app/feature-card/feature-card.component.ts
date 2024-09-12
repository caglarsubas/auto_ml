import { Component, Inject, OnInit, PLATFORM_ID } from '@angular/core';
import { isPlatformBrowser } from '@angular/common';
import { MAT_DIALOG_DATA, MatDialogRef } from '@angular/material/dialog';
// Update this import statement to match your project structure
import { DataService } from '../services/data.service';
import { HttpErrorResponse } from '@angular/common/http';

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

  constructor(
    @Inject(MAT_DIALOG_DATA) public data: { fileId: string, columnName: string },
    @Inject(PLATFORM_ID) platformId: Object,
    private dataService: DataService
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
      xaxis: { title: this.featureData.Feature_Name },
      yaxis: { title: 'Frequency' }
    };
  
    try {
      if (this.isNumerical()) {
        const histogramData = this.featureData.Descriptive_Stats.histogram_data;
        if (histogramData && histogramData.length > 0) {
          plotData.push({
            x: histogramData,
            type: 'histogram',
            marker: {
              color: 'rgba(100, 149, 237, 0.7)',
              line: {
                color: 'rgba(100, 149, 237, 1)',
                width: 1
              }
            }
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
              }
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
}