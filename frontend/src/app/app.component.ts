import { Component, OnInit, Inject, PLATFORM_ID } from '@angular/core';
import { Router, NavigationEnd, Event } from '@angular/router';
import { filter } from 'rxjs/operators';
import { isPlatformBrowser } from '@angular/common';
import { AuthService } from './services/auth.service';  // Make sure to import AuthService

@Component({
  selector: 'app-root',
  templateUrl: './app.component.html',
  styleUrl: './app.component.css'
})

export class AppComponent implements OnInit {
  title = 'frontend';
  showMagnifier = false;
  magnifierX = 0;
  magnifierY = 0;
  bgPosX = 0;
  bgPosY = 0;
  readonly magnifierSize = 120; // Diameter of the magnifier in pixels
  readonly zoomLevel = 2.5; // Magnification level
  isLoginPage = false;
  isHomePage = false;
  isBrowser: boolean;

  constructor(
    private router: Router,
    @Inject(PLATFORM_ID) private platformId: Object,
    private authService: AuthService  // Inject AuthService
  ) {
    this.isBrowser = isPlatformBrowser(this.platformId);
  }

  ngOnInit() {
    if (this.isBrowser) {
      this.router.events.pipe(
        filter((event: Event): event is NavigationEnd => event instanceof NavigationEnd)
      ).subscribe((event: NavigationEnd) => {
        this.isLoginPage = event.urlAfterRedirects === '/login';
        this.isHomePage = event.urlAfterRedirects.startsWith('/home');
      });
    }
  }

  updateMagnifier(event: MouseEvent) {
    if (this.isBrowser) {
      const img = event.target as HTMLImageElement;
      const rect = img.getBoundingClientRect();
      
      // Cursor position relative to image
      const cursorX = event.clientX - rect.left;
      const cursorY = event.clientY - rect.top;
      
      // Position magnifier centered on cursor
      this.magnifierX = cursorX - this.magnifierSize / 2;
      this.magnifierY = cursorY - this.magnifierSize / 2;
      
      // Calculate background position to center the zoomed area on cursor
      // The zoomed image is zoomLevel times larger, so we offset accordingly
      this.bgPosX = (cursorX * this.zoomLevel) - (this.magnifierSize / 2);
      this.bgPosY = (cursorY * this.zoomLevel) - (this.magnifierSize / 2);
    }
  }
  
  shouldShowFullMenu(): boolean {
    return !this.isLoginPage && !this.isHomePage;
  }

  onSignOut() {
    this.authService.logout();
    this.router.navigate(['/login']);
  }
  
}