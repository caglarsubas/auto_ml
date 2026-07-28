import { NgModule } from '@angular/core';
import { BrowserModule } from '@angular/platform-browser';
import { HttpClientModule } from '@angular/common/http';
import { BrowserAnimationsModule } from '@angular/platform-browser/animations';
import { MatToolbarModule } from '@angular/material/toolbar';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatInputModule } from '@angular/material/input';
import { MatTableModule } from '@angular/material/table';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSnackBarModule } from '@angular/material/snack-bar';
import { MatDialogModule } from '@angular/material/dialog';
import { FormsModule } from '@angular/forms';  // Import FormsModule
import { MatCheckboxModule } from '@angular/material/checkbox';  // Ensure you have this for MatCheckbox
import { MatMenuModule } from '@angular/material/menu';
import { MatTooltipModule } from '@angular/material/tooltip';
import { MatSelectModule } from '@angular/material/select';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatOptionModule } from '@angular/material/core';
import { MatTabsModule } from '@angular/material/tabs';
import { MatRippleModule } from '@angular/material/core';
import { MatIconModule } from '@angular/material/icon';

import { AppRoutingModule } from './app-routing.module';
import { AppComponent } from './app.component';
import { DeclarationComponent } from './declaration/declaration.component';
import { FeatureCardComponent } from './feature-card/feature-card.component';
import { PreprocessingComponent } from './preprocessing/preprocessing.component';
import { ModelingComponent } from './modeling/modeling.component';
import { EvaluationComponent } from './evaluation/evaluation.component';
import { DeploymentComponent } from './deployment/deployment.component';
import { ModelDevelopmentComponent } from './model-development/model-development.component';
import { HomeComponent } from './home/home.component';
import { SharedService } from './services/shared.service';
import { LoginComponent } from './login/login.component';
import { AiChatPanelComponent } from './ai-chat-panel/ai-chat-panel.component';
import { AiAssistantService } from './services/ai-assistant.service';
import { PipelineCodelineComponent } from './pipeline-codeline/pipeline-codeline.component';
import { FeatureStoreComponent } from './feature-store/feature-store.component';

@NgModule({
  declarations: [
    AppComponent,
    DeclarationComponent,
    FeatureCardComponent,
    PreprocessingComponent,
    ModelingComponent,
    EvaluationComponent,
    DeploymentComponent,
    ModelDevelopmentComponent,
    HomeComponent,
    LoginComponent,
    AiChatPanelComponent,
    PipelineCodelineComponent,
    FeatureStoreComponent
  ],
  imports: [
    BrowserModule,
    AppRoutingModule,
    HttpClientModule,
    BrowserAnimationsModule,
    MatToolbarModule,
    MatButtonModule,
    MatCardModule,
    MatInputModule,
    MatTableModule,
    MatProgressBarModule,
    MatProgressSpinnerModule,
    MatSnackBarModule,
    MatDialogModule,
    FormsModule,
    MatCheckboxModule,
    MatMenuModule,
    MatTooltipModule,
    MatSelectModule,
    MatFormFieldModule,
    MatOptionModule,
    MatTabsModule,
    MatRippleModule,
    MatIconModule,
  ],
  providers: [
    SharedService,
    AiAssistantService,
  ],
  bootstrap: [AppComponent]
})
export class AppModule { }