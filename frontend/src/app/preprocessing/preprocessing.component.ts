import { Component, ChangeDetectionStrategy } from '@angular/core';

@Component({
  selector: 'app-preprocessing',
  templateUrl: './preprocessing.component.html',
  styleUrls: ['./preprocessing.component.css'],
  changeDetection: ChangeDetectionStrategy.Eager,
  standalone: false,
})
export class PreprocessingComponent {
  // This component is now mostly empty as its content has been moved to the ModelDevelopmentComponent
}
