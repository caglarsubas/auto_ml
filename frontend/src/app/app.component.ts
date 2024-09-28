import { Component } from '@angular/core';

@Component({
  selector: 'app-root',
  templateUrl: './app.component.html',
  styleUrl: './app.component.css'
})
export class AppComponent {
  title = 'frontend';
  showMagnifier = false;
  magnifierX = 0;
  magnifierY = 0;
  readonly magnifierSize = 100; // Diameter of the magnifier in pixels

  updateMagnifier(event: MouseEvent) {
    const rect = (event.target as HTMLElement).getBoundingClientRect();
    this.magnifierX = event.clientX - rect.left - this.magnifierSize / 2;
    this.magnifierY = event.clientY - rect.top - this.magnifierSize / 2;
  }
}